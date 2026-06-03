from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from boardroom_os.contracts.acceptance import (
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
)
from boardroom_os.contracts.evidence_obligation import (
    EvidenceObligation,
    RequiredArtifactType,
    RequiredVerifier,
)
from boardroom_os.contracts.package import IntegrationBoundary, PackageCommand, PackageContract, PackageProjectType
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.evidence.claim import (
    EvidenceArtifactRef,
    EvidenceClaim,
    EvidenceClaimRef,
    EvidenceClaimSourceKind,
    build_evidence_claim_from_live_blackbox,
)
from boardroom_os.evidence.live_blackbox import (
    LiveBlackboxIntegrationEvidence,
    LiveBlackboxIntegrationEvidenceRef,
    LiveBlackboxIntegrationVerifier,
    LiveBlackboxProbeResult,
    LiveBlackboxVerifierInput,
)
from boardroom_os.evidence.verifier import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactSha256,
    EvidencePurposePolicy,
    EvidencePurposeRule,
    EvidenceVerificationInput,
    EvidenceVerifier,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.verification_run import VerificationRunRef
from tests.evidence.test_evidence_verifier import (
    _acceptance_contract,
    _execution_package,
    _provider_attempt,
)
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook_registry

_NOW = datetime(2026, 6, 2, 9, 0, tzinfo=UTC)
_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def _frontend_service_command() -> tuple[str, ...]:
    return (
        "python",
        "-c",
        (
            "import os; "
            "from functools import partial; "
            "from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer; "
            "handler = partial(SimpleHTTPRequestHandler, directory='frontend'); "
            "port = int(os.environ.get('FRONTEND_PORT', '5173')); "
            "ThreadingHTTPServer(('127.0.0.1', port), handler).serve_forever()"
        ),
    )


def _probe(
    probe_ref: str,
    *,
    acceptance_ref: str,
    service_run_refs: tuple[str, ...],
    command_ids: tuple[str, ...],
    probe_url: str | None = None,
    passed: bool = True,
    observed_facts: dict[str, object] | None = None,
) -> LiveBlackboxProbeResult:
    return LiveBlackboxProbeResult(
        probe_ref=probe_ref,
        acceptance_refs=(AcceptanceRef(value=acceptance_ref),),
        service_run_refs=tuple(service_run_refs),
        command_ids=tuple(command_ids),
        probe_url=probe_url,
        status_code=200 if passed else 500,
        passed=passed,
        observed_facts=observed_facts or {"workflow": probe_ref, "real_probe": True},
        body_sha256=_HASH,
        probed_at=_NOW,
    )


def _evidence(
    *,
    probes: tuple[LiveBlackboxProbeResult, ...] | None = None,
) -> LiveBlackboxIntegrationEvidence:
    return LiveBlackboxIntegrationEvidence(
        live_blackbox_evidence_id=LiveBlackboxIntegrationEvidenceRef(
            value="live-blackbox.inventory-app"
        ),
        package_contract_ref=ContractId(value="package-contract-inventory-app"),
        backend_command_id=ContractId(value="run-backend"),
        frontend_command_id=ContractId(value="run-frontend"),
        backend_service_run_ref="service-run.backend",
        frontend_service_run_ref="service-run.frontend",
        probes=probes
        or (
            _probe(
                "backend-http-workflow",
                acceptance_ref="AC-INVENTORY-BACKEND",
                service_run_refs=("service-run.backend",),
                command_ids=("run-backend",),
                probe_url="http://127.0.0.1:8000/api/inventory",
                observed_facts={"created_item_id": "sku-1", "listed_after_create": True},
            ),
            _probe(
                "frontend-live-workflow",
                acceptance_ref="AC-INVENTORY-FRONTEND",
                service_run_refs=("service-run.backend", "service-run.frontend"),
                command_ids=("run-backend", "run-frontend"),
                probe_url="http://127.0.0.1:5173/",
                observed_facts={
                    "browser_observed_backend_origin": "http://127.0.0.1:8000",
                    "used_synthetic_fetch": False,
                },
            ),
        ),
        generated_at=_NOW,
    )


def _package_contract() -> PackageContract:
    return PackageContract(
        package_contract_id=ContractId(value="package-contract-inventory-app"),
        project_charter_ref=ContractId(value="project-charter.inventory-app"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            SourceSurface(
                source_surface_ref=SourceSurfaceRef(value="app"),
                name="Inventory app",
                paths=("backend", "frontend"),
                owned_by=OwnerSeatRef(value="owner.app"),
                acceptance_refs=(AcceptanceRef(value="AC-INVENTORY-FRONTEND"),),
                required_tests=(RequiredTestRef(value="live-blackbox"),),
            ),
        ),
        run_commands=(
            PackageCommand(
                command_id=ContractId(value="run-backend"),
                label="Run backend",
                command=("python", "-m", "inventory_service"),
                cwd=".",
            ),
            PackageCommand(
                command_id=ContractId(value="run-frontend"),
                label="Run frontend",
                command=_frontend_service_command(),
                cwd=".",
            ),
        ),
        test_commands=(
            PackageCommand(
                command_id=ContractId(value="test-live"),
                label="Run live tests",
                command=("python", "-m", "pytest"),
                cwd=".",
            ),
        ),
        integration_boundaries=(IntegrationBoundary(value="live-http"),),
        docs_required=False,
        closeout_required=True,
    )


def _obligation(artifact_type: str, acceptance_ref: str) -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value=f"evidence.{artifact_type}"),
        acceptance_refs=(AcceptanceRef(value=acceptance_ref),),
        source_surface_refs=(SourceSurfaceRef(value="app"),),
        required_artifact_type=RequiredArtifactType(value=artifact_type),
        required_verifier=RequiredVerifier(value="live_blackbox"),
        blocking=True,
    )


def test_live_blackbox_verifier_accepts_generic_probe_facts_without_project_shape_markers() -> None:
    evidence = _evidence()

    result = LiveBlackboxIntegrationVerifier().verify(
        LiveBlackboxVerifierInput(
            evidence=evidence,
            package_contract=_package_contract(),
            service_runs=_service_runs(),
        )
    )

    assert result.success is True


def test_live_blackbox_claim_uses_first_class_source_kind_and_matching_probe_artifact() -> None:
    evidence = _evidence()
    claim = build_evidence_claim_from_live_blackbox(
        evidence=evidence,
        evidence_obligation=_obligation(
            "live_frontend_backend_integration_evidence",
            "AC-INVENTORY-FRONTEND",
        ),
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.inventory.tests"),
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Live inventory app blackbox integration evidence.",
    )

    assert claim.source_kind is EvidenceClaimSourceKind.LIVE_BLACKBOX
    assert claim.source_ref == evidence.live_blackbox_evidence_id.value
    assert [artifact_ref.value for artifact_ref in claim.artifact_refs] == [
        "live-blackbox.inventory-app.frontend-live-workflow"
    ]


def test_live_blackbox_claim_becomes_verified_evidence() -> None:
    evidence = _evidence()
    obligation = _obligation(
        "custom_live_blackbox_artifact",
        "AC-INVENTORY-FRONTEND",
    )
    claim = build_evidence_claim_from_live_blackbox(
        evidence=evidence,
        evidence_obligation=obligation,
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Live frontend/backend blackbox evidence.",
    )

    result = EvidenceVerifier().verify(
        EvidenceVerificationInput(
            claim=claim,
            evidence_obligation=obligation,
            active_acceptance_contract=_acceptance_contract(
                criteria=(
                    AcceptanceCriterion(
                        acceptance_ref=AcceptanceRef(value="AC-INVENTORY-FRONTEND"),
                        statement="Frontend talks to the live backend.",
                        evidence_required=(EvidenceRequirement(value="custom_live_blackbox_artifact"),),
                        blocking=True,
                        source_surface_refs=(SourceSurfaceRef(value="app"),),
                        verification_strategy=VerificationStrategy(value="live_blackbox"),
                    ),
                )
            ),
            artifact_manifest=_artifact_manifest(claim=claim, evidence=evidence, artifact_type=obligation.required_artifact_type.value),
            purpose_policy=_purpose_policy(obligation),
            provider_attempts=(_provider_attempt(),),
            execution_packages=(_execution_package(),),
            role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
            active_package_contract=_package_contract(),
            service_runs=_service_runs(),
            live_blackbox_evidence=(evidence,),
            verified_at=_NOW,
        )
    )

    assert result.success is True
    assert result.verified_evidence is not None
    assert result.verified_evidence.source_kind is EvidenceClaimSourceKind.LIVE_BLACKBOX
    assert result.verified_evidence.source_ref == evidence.live_blackbox_evidence_id.value


def test_evidence_verifier_rejects_live_blackbox_without_bound_service_runs() -> None:
    evidence = _evidence()
    obligation = _obligation(
        "custom_live_blackbox_artifact",
        "AC-INVENTORY-FRONTEND",
    )
    claim = build_evidence_claim_from_live_blackbox(
        evidence=evidence,
        evidence_obligation=obligation,
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Live frontend/backend blackbox evidence.",
    )

    result = EvidenceVerifier().verify(
        EvidenceVerificationInput(
            claim=claim,
            evidence_obligation=obligation,
            active_acceptance_contract=_acceptance_contract(
                criteria=(
                    AcceptanceCriterion(
                        acceptance_ref=AcceptanceRef(value="AC-INVENTORY-FRONTEND"),
                        statement="Frontend talks to the live backend.",
                        evidence_required=(EvidenceRequirement(value="custom_live_blackbox_artifact"),),
                        blocking=True,
                        source_surface_refs=(SourceSurfaceRef(value="app"),),
                        verification_strategy=VerificationStrategy(value="live_blackbox"),
                    ),
                )
            ),
            artifact_manifest=_artifact_manifest(claim=claim, evidence=evidence, artifact_type=obligation.required_artifact_type.value),
            purpose_policy=_purpose_policy(obligation),
            provider_attempts=(_provider_attempt(),),
            execution_packages=(_execution_package(),),
            role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
            active_package_contract=_package_contract(),
            live_blackbox_evidence=(evidence,),
            verified_at=_NOW,
        )
    )

    assert result.success is False
    assert result.verified_evidence is None
    assert any("service run" in blocker.message for blocker in result.blockers)


@pytest.mark.parametrize(
    "artifact_type",
    [
        "sqlite_persistence_http_evidence",
        "custom_live_blackbox_artifact",
    ],
)
def test_evidence_verifier_rejects_verification_run_claim_when_obligation_requires_live_blackbox(
    artifact_type: str,
) -> None:
    obligation = _obligation(
        artifact_type,
        "AC-INVENTORY-FRONTEND",
    )
    run_ref = VerificationRunRef(value="verification-run.integration")
    claim = EvidenceClaim(
        evidence_claim_id=EvidenceClaimRef(value="evidence-claim.verification-run.integration"),
        evidence_obligation_ref=obligation.evidence_obligation_id,
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        source_kind=EvidenceClaimSourceKind.VERIFICATION_RUN,
        source_ref=run_ref.value,
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        required_artifact_type=obligation.required_artifact_type,
        acceptance_refs=obligation.acceptance_refs,
        source_surface_refs=obligation.source_surface_refs,
        artifact_refs=(
            EvidenceArtifactRef(value=f"command-output.{run_ref.value}.stdout"),
            EvidenceArtifactRef(value=f"command-output.{run_ref.value}.stderr"),
        ),
        verification_run_refs=(run_ref,),
        summary="Command output must not satisfy a live blackbox obligation.",
    )

    result = EvidenceVerifier().verify(
        EvidenceVerificationInput(
            claim=claim,
            evidence_obligation=obligation,
            active_acceptance_contract=_acceptance_contract(
                criteria=(
                    AcceptanceCriterion(
                        acceptance_ref=AcceptanceRef(value="AC-INVENTORY-FRONTEND"),
                        statement="Frontend talks to the live backend.",
                        evidence_required=(EvidenceRequirement(value=artifact_type),),
                        blocking=True,
                        source_surface_refs=(SourceSurfaceRef(value="app"),),
                        verification_strategy=VerificationStrategy(value="live_blackbox"),
                    ),
                )
            ),
            artifact_manifest=ArtifactManifest(
                entries=tuple(
                    ArtifactManifestEntry(
                        artifact_ref=artifact_ref,
                        sha256=ArtifactSha256(value="1" * 64),
                        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
                        source_ref=run_ref.value,
                        artifact_kind=f"{obligation.required_artifact_type.value}_{index}",
                    )
                    for index, artifact_ref in enumerate(claim.artifact_refs, start=1)
                )
            ),
            purpose_policy=_purpose_policy(obligation),
            provider_attempts=(_provider_attempt(),),
            execution_packages=(_execution_package(),),
            verification_runs=(_verification_run(run_ref),),
            role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
            verified_at=_NOW,
        )
    )

    assert result.success is False
    assert result.verified_evidence is None
    assert any("live blackbox" in blocker.message for blocker in result.blockers)


def test_evidence_verifier_rejects_live_blackbox_evidence_that_fails_blackbox_validator() -> None:
    evidence = _evidence(
        probes=(
            _probe(
                "failed-frontend-live-workflow",
                acceptance_ref="AC-INVENTORY-FRONTEND",
                service_run_refs=("service-run.backend", "service-run.frontend"),
                command_ids=("run-backend", "run-frontend"),
                probe_url="http://127.0.0.1:5173/",
                passed=False,
            ),
        )
    )
    obligation = _obligation(
        "custom_live_blackbox_artifact",
        "AC-INVENTORY-FRONTEND",
    )
    claim = build_evidence_claim_from_live_blackbox(
        evidence=evidence,
        evidence_obligation=obligation,
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Bad live blackbox evidence must fail closed.",
    )

    result = EvidenceVerifier().verify(
        EvidenceVerificationInput(
            claim=claim,
            evidence_obligation=obligation,
            active_acceptance_contract=_acceptance_contract(
                criteria=(
                    AcceptanceCriterion(
                        acceptance_ref=AcceptanceRef(value="AC-INVENTORY-FRONTEND"),
                        statement="Frontend talks to the live backend.",
                        evidence_required=(EvidenceRequirement(value="custom_live_blackbox_artifact"),),
                        blocking=True,
                        source_surface_refs=(SourceSurfaceRef(value="app"),),
                        verification_strategy=VerificationStrategy(value="live_blackbox"),
                    ),
                )
            ),
            artifact_manifest=_artifact_manifest(claim=claim, evidence=evidence, artifact_type=obligation.required_artifact_type.value),
            purpose_policy=_purpose_policy(obligation),
            provider_attempts=(_provider_attempt(),),
            execution_packages=(_execution_package(),),
            role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
            active_package_contract=_package_contract(),
            service_runs=_service_runs(),
            live_blackbox_evidence=(evidence,),
            verified_at=_NOW,
        )
    )

    assert result.success is False
    assert result.verified_evidence is None


def _artifact_manifest(
    *,
    claim: EvidenceClaim,
    evidence: LiveBlackboxIntegrationEvidence,
    artifact_type: str,
) -> ArtifactManifest:
    return ArtifactManifest(
        entries=tuple(
            ArtifactManifestEntry(
                artifact_ref=artifact_ref,
                sha256=ArtifactSha256(value="1" * 64),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
                source_ref=evidence.live_blackbox_evidence_id.value,
                artifact_kind=f"{artifact_type}_{index}",
            )
            for index, artifact_ref in enumerate(claim.artifact_refs, start=1)
        )
    )


def _purpose_policy(obligation: EvidenceObligation) -> EvidencePurposePolicy:
    return EvidencePurposePolicy(
        rules=(
            EvidencePurposeRule(
                required_artifact_type=obligation.required_artifact_type,
                allowed_purposes=(EvidencePurpose.IMPLEMENTATION,),
            ),
        )
    )


def _service_runs():
    return (
        _service_run(
            "service-run.backend",
            command_id="run-backend",
            command=("python", "-m", "inventory_service"),
            cwd=".",
            readiness_url="http://127.0.0.1:8000/ready",
            environment_overrides={"PORT": "8000"},
        ),
        _service_run(
            "service-run.frontend",
            command_id="run-frontend",
            command=_frontend_service_command(),
            cwd=".",
            readiness_url="http://127.0.0.1:5173/",
            environment_overrides={"FRONTEND_PORT": "5173"},
        ),
    )


def _service_run(
    service_run_ref: str,
    *,
    command_id: str,
    command: tuple[str, ...],
    cwd: str,
    readiness_url: str,
    environment_overrides: dict[str, str],
):
    from boardroom_os.evidence.service_run import ServiceRunEvidence
    from boardroom_os.execution.verification_run import (
        CommandOutputRef,
        EnvironmentProfileRef,
        RunnerRef,
        WorkspaceSnapshotRef,
    )

    return ServiceRunEvidence(
        service_run_evidence_id=service_run_ref,
        execution_package_ref="exec.backend.1",
        ticket_ref="ticket.backend.1",
        command_id=command_id,
        command=command,
        cwd=cwd,
        process_id=4321,
        readiness_url=readiness_url,
        probe_status_code=200,
        probe_body_sha256=_HASH,
        stdout_ref=CommandOutputRef(value=f"command-output.{service_run_ref}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.{service_run_ref}.stderr"),
        started_at=_NOW,
        ready_at=_NOW,
        stopped_at=None,
        runner_ref=RunnerRef(value="runner.local-service"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.service"),
        environment_overrides=environment_overrides,
    )


def _verification_run(run_ref: VerificationRunRef):
    from boardroom_os.execution.verification_run import (
        CommandOutputRef,
        EnvironmentProfileRef,
        RunnerRef,
        VerificationRun,
        VerificationRunStatus,
        WorkspaceSnapshotRef,
    )

    return VerificationRun(
        verification_run_id=run_ref,
        execution_package_ref="exec.backend.1",
        ticket_ref="ticket.backend.1",
        command_id="test-live",
        command=("python", "-m", "pytest"),
        cwd=".",
        exit_code=0,
        status=VerificationRunStatus.PASSED,
        stdout_ref=CommandOutputRef(value=f"command-output.{run_ref.value}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.{run_ref.value}.stderr"),
        duration_ms=1000,
        started_at=_NOW,
        finished_at=_NOW + timedelta(seconds=1),
        runner_ref=RunnerRef(value="runner.local"),
        environment_profile_ref=EnvironmentProfileRef(value="env.local"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.local"),
    )
