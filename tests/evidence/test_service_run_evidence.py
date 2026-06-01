from __future__ import annotations

from datetime import UTC, datetime

from boardroom_os.contracts.acceptance import (
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
)
from boardroom_os.contracts.evidence_obligation import EvidenceObligation, RequiredArtifactType, RequiredVerifier
from boardroom_os.contracts.types import AcceptanceRef, ContractId, EvidenceObligationRef, SourceSurfaceRef
from boardroom_os.evidence.claim import EvidenceArtifactRef, EvidenceClaimSourceKind, build_evidence_claim_from_service_run
from boardroom_os.evidence.service_run import ServiceRunEvidence
from boardroom_os.evidence.verifier import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactSha256,
    EvidencePurposePolicy,
    EvidencePurposeRule,
    EvidenceVerifier,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.verification_run import CommandOutputRef, EnvironmentProfileRef, RunnerRef, WorkspaceSnapshotRef
from tests.evidence.test_evidence_verifier import _acceptance_contract, _execution_package, _provider_attempt
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook_registry

_NOW = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
_BODY_SHA256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def _service_run() -> ServiceRunEvidence:
    return ServiceRunEvidence(
        service_run_evidence_id="service-run.run-app",
        execution_package_ref="exec.backend.1",
        ticket_ref="ticket.backend.1",
        command_id="run-app",
        command=("python", "app.py"),
        cwd=".",
        process_id=4321,
        readiness_url="http://127.0.0.1:8000/health",
        probe_status_code=200,
        probe_body_sha256=_BODY_SHA256,
        stdout_ref=CommandOutputRef(value="command-output.service-run.run-app.stdout"),
        stderr_ref=CommandOutputRef(value="command-output.service-run.run-app.stderr"),
        started_at=_NOW,
        ready_at=_NOW,
        stopped_at=None,
        runner_ref=RunnerRef(value="runner.local-service"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.service"),
    )


def _obligation() -> EvidenceObligation:
    return EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="evidence.service.run"),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        required_artifact_type=RequiredArtifactType(value="service_run"),
        required_verifier=RequiredVerifier(value="service_runner"),
        blocking=True,
    )


def _manifest(service_run: ServiceRunEvidence) -> ArtifactManifest:
    return ArtifactManifest(
        entries=(
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=service_run.stdout_ref.value),
                sha256=ArtifactSha256(value="1" * 64),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
                source_ref=service_run.service_run_evidence_id.value,
                artifact_kind="service_stdout",
            ),
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=service_run.stderr_ref.value),
                sha256=ArtifactSha256(value="2" * 64),
                producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
                source_ref=service_run.service_run_evidence_id.value,
                artifact_kind="service_stderr",
            ),
        )
    )


def test_service_run_claim_becomes_verified_evidence() -> None:
    service_run = _service_run()
    obligation = _obligation()
    claim = build_evidence_claim_from_service_run(
        service_run=service_run,
        evidence_obligation=obligation,
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Backend service readiness evidence.",
    )

    result = EvidenceVerifier().verify(
        verification_input=__import__(
            "boardroom_os.evidence.verifier",
            fromlist=["EvidenceVerificationInput"],
        ).EvidenceVerificationInput(
            claim=claim,
            evidence_obligation=obligation,
            active_acceptance_contract=_acceptance_contract(
                criteria=(
                    AcceptanceCriterion(
                        acceptance_ref=AcceptanceRef(value="AC-BACKEND"),
                        statement="Backend service is reachable over HTTP.",
                        evidence_required=(EvidenceRequirement(value="service readiness probe"),),
                        blocking=True,
                        source_surface_refs=(SourceSurfaceRef(value="surface.backend"),),
                        verification_strategy=VerificationStrategy(value="service_runner"),
                    ),
                )
            ),
            artifact_manifest=_manifest(service_run),
            purpose_policy=EvidencePurposePolicy(
                rules=(
                    EvidencePurposeRule(
                        required_artifact_type=RequiredArtifactType(value="service_run"),
                        allowed_purposes=(EvidencePurpose.IMPLEMENTATION,),
                    ),
                )
            ),
            provider_attempts=(_provider_attempt(),),
            execution_packages=(_execution_package(),),
            service_runs=(service_run,),
            role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
            verified_at=_NOW,
        )
    )

    assert result.success is True
    assert result.verified_evidence is not None
    assert result.verified_evidence.source_kind is EvidenceClaimSourceKind.SERVICE_RUN
    assert result.verified_evidence.source_ref == service_run.service_run_evidence_id.value
    assert result.verified_evidence.verification_run_refs == ()
