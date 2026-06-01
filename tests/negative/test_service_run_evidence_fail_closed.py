from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.adapters.process_runner import ServiceRunner, ServiceRunnerError, ServiceRunnerInput
from boardroom_os.contracts.acceptance import AcceptanceCriterion, EvidenceRequirement, VerificationStrategy
from boardroom_os.contracts.evidence_obligation import RequiredArtifactType
from boardroom_os.contracts.types import ContractId
from boardroom_os.evidence.claim import build_evidence_claim_from_service_run
from boardroom_os.evidence.service_run import ServiceRunEvidence, stderr_ref_for_service_run, stdout_ref_for_service_run
from boardroom_os.evidence.verifier import (
    EvidencePurposePolicy,
    EvidencePurposeRule,
    EvidenceVerificationBlockerCode,
    EvidenceVerificationInput,
    EvidenceVerifier,
)
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.verification_run import (
    CommandOutputRef,
    EnvironmentProfileRef,
    RunnerRef,
    WorkspaceSnapshotRef,
)
from tests.evidence.test_evidence_verifier import (
    _evidence_obligation,
    _input,
    _purpose_policy,
    _verification_run,
    _verification_run_claim,
    _verification_run_manifest,
)
from tests.evidence.test_service_run_evidence import _manifest as _service_manifest
from tests.evidence.test_service_run_evidence import _obligation as _service_obligation
from tests.evidence.test_service_run_evidence import _service_run as _verifiable_service_run
from tests.evidence.test_evidence_verifier import _acceptance_contract, _provider_attempt
from tests.execution.test_command_runner import _execution_package, _package_contract, _python_command
from tests.fixtures.execution.role_prompt_hooks import baseline_role_prompt_hook_registry

_VERIFY_ERRORS = (ValueError, ValidationError)
_BODY_SHA256 = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
_STARTED_AT = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
_READY_AT = datetime(2026, 6, 1, 9, 0, 1, tzinfo=UTC)


def _service_fields(**overrides: object) -> dict[str, object]:
    fields: dict[str, object] = {
        "service_run_evidence_id": "service-run.command.run-app",
        "execution_package_ref": "execution-package.command",
        "ticket_ref": "ticket.command",
        "command_id": "run-app",
        "command": (sys.executable, "app.py"),
        "cwd": ".",
        "process_id": 4321,
        "readiness_url": "http://127.0.0.1:8000/health",
        "probe_status_code": 200,
        "probe_body_sha256": _BODY_SHA256,
        "stdout_ref": CommandOutputRef(value="command-output.service-run.command.run-app.stdout"),
        "stderr_ref": CommandOutputRef(value="command-output.service-run.command.run-app.stderr"),
        "started_at": _STARTED_AT,
        "ready_at": _READY_AT,
        "stopped_at": None,
        "runner_ref": RunnerRef(value="runner.local-service"),
        "environment_profile_ref": EnvironmentProfileRef(value="environment.local"),
        "workspace_snapshot_ref": WorkspaceSnapshotRef(value="workspace-snapshot.service"),
    }
    fields.update(overrides)
    return fields


def test_service_run_evidence_rejects_process_id_without_readiness_probe() -> None:
    fields = _service_fields()
    del fields["readiness_url"]

    with pytest.raises(_VERIFY_ERRORS, match="readiness"):
        ServiceRunEvidence(**fields)


def test_service_run_evidence_rejects_non_successful_probe_status() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="2xx|readiness|probe"):
        ServiceRunEvidence(**_service_fields(probe_status_code=503))


def test_service_run_evidence_rejects_ready_at_before_started_at() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="ready_at"):
        ServiceRunEvidence(
            **_service_fields(
                ready_at=_STARTED_AT - timedelta(milliseconds=1),
            )
        )


def test_service_run_evidence_rejects_service_that_stopped_before_readiness() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="stopped_at|ready"):
        ServiceRunEvidence(
            **_service_fields(
                stopped_at=_STARTED_AT,
            )
        )


def test_service_run_evidence_rejects_naive_timestamps() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="timezone-aware"):
        ServiceRunEvidence(**_service_fields(started_at=datetime(2026, 6, 1, 9, 0)))


def test_service_runner_rejects_process_that_exits_before_readiness(tmp_path: Path) -> None:
    command = _python_command(
        command_id="run-app",
        label="Run app",
        cwd=".",
    ).model_copy(update={"command": (sys.executable, "-c", "print('bye')")})

    with pytest.raises(ServiceRunnerError, match="exited before readiness|readiness"):
        ServiceRunner().run(
            ServiceRunnerInput(
                execution_package=_execution_package(command),
                package_contract=_package_contract(command),
                command_id=ContractId(value="run-app"),
                package_root=tmp_path,
                readiness_url="http://127.0.0.1:9/health",
                runner_ref=RunnerRef(value="runner.local-service"),
                environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
                workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.service"),
                timeout_seconds=0.5,
                poll_interval_seconds=0.05,
            )
        )


def test_service_run_required_artifact_rejects_verification_run_source_kind() -> None:
    run = _verification_run()
    obligation = _evidence_obligation(
        required_artifact_type=RequiredArtifactType(value="service_run")
    )
    claim = _verification_run_claim(run).model_copy(
        update={
            "evidence_obligation_ref": obligation.evidence_obligation_id,
            "required_artifact_type": obligation.required_artifact_type,
        }
    )

    result = EvidenceVerifier().verify(
        _input(
            claim=claim,
            evidence_obligation=obligation,
            artifact_manifest=_verification_run_manifest(run),
            purpose_policy=_purpose_policy(
                required_artifact_type=RequiredArtifactType(value="service_run")
            ),
            verification_runs=(run,),
        )
    )

    assert result.verified_evidence is None
    assert any(
        blocker.code is EvidenceVerificationBlockerCode.MISSING_SERVICE_RUN
        for blocker in result.blockers
    )


def test_service_run_verifier_rejects_non_canonical_output_refs() -> None:
    service_run = _verifiable_service_run().model_copy(
        update={
            "stdout_ref": CommandOutputRef(value="command-output.forged.stdout"),
            "stderr_ref": CommandOutputRef(value="command-output.forged.stderr"),
        }
    )
    obligation = _service_obligation()
    claim = build_evidence_claim_from_service_run(
        service_run=service_run,
        evidence_obligation=obligation,
        producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend"),
        acceptance_refs=obligation.acceptance_refs,
        source_surface_refs=obligation.source_surface_refs,
        expected_purpose=EvidencePurpose.IMPLEMENTATION,
        summary="Forged output refs must not verify.",
    )

    result = EvidenceVerifier().verify(
        EvidenceVerificationInput(
            claim=claim,
            evidence_obligation=obligation,
            active_acceptance_contract=_acceptance_contract(
                criteria=(
                    AcceptanceCriterion(
                        acceptance_ref=obligation.acceptance_refs[0],
                        statement="Backend service is reachable over HTTP.",
                        evidence_required=(
                            EvidenceRequirement(value="service readiness probe"),
                        ),
                        blocking=True,
                        source_surface_refs=obligation.source_surface_refs,
                        verification_strategy=VerificationStrategy(value="service_runner"),
                    ),
                )
            ),
            artifact_manifest=_service_manifest(service_run),
            purpose_policy=EvidencePurposePolicy(
                rules=(
                    EvidencePurposeRule(
                        required_artifact_type=obligation.required_artifact_type,
                        allowed_purposes=(EvidencePurpose.IMPLEMENTATION,),
                    ),
                )
            ),
            provider_attempts=(_provider_attempt(),),
            execution_packages=(_execution_package(),),
            service_runs=(service_run,),
            role_prompt_hook_registry=baseline_role_prompt_hook_registry(),
            verified_at=_STARTED_AT,
        )
    )

    assert result.verified_evidence is None
    assert any(
        blocker.code is EvidenceVerificationBlockerCode.SERVICE_RUN_ARTIFACT_REFS_MISMATCH
        for blocker in result.blockers
    )
    assert stdout_ref_for_service_run(service_run.service_run_evidence_id) != service_run.stdout_ref
    assert stderr_ref_for_service_run(service_run.service_run_evidence_id) != service_run.stderr_ref
