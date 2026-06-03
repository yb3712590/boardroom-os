from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.package import IntegrationBoundary, PackageCommand, PackageContract, PackageProjectType
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, SourceSurfaceRef
from boardroom_os.evidence.live_blackbox import (
    LiveBlackboxIntegrationEvidence,
    LiveBlackboxIntegrationEvidenceRef,
    LiveBlackboxIntegrationVerifier,
    LiveBlackboxProbeResult,
    LiveBlackboxVerifierInput,
)
from boardroom_os.evidence.service_run import ServiceRunEvidence
from boardroom_os.execution.verification_run import (
    CommandOutputRef,
    EnvironmentProfileRef,
    RunnerRef,
    WorkspaceSnapshotRef,
)

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
    *,
    probe_ref: str = "frontend-live-workflow",
    service_run_refs: tuple[str, ...] = ("service-run.backend", "service-run.frontend"),
    command_ids: tuple[str, ...] = ("run-backend", "run-frontend"),
    probe_url: str | None = "http://127.0.0.1:5173/",
    passed: bool = True,
) -> LiveBlackboxProbeResult:
    return LiveBlackboxProbeResult(
        probe_ref=probe_ref,
        acceptance_refs=(AcceptanceRef(value="AC-GENERIC-LIVE-FRONTEND"),),
        service_run_refs=tuple(service_run_refs),
        command_ids=tuple(command_ids),
        probe_url=probe_url,
        status_code=200 if passed else 500,
        passed=passed,
        observed_facts={"live_workflow_executed": passed},
        body_sha256=_HASH,
        probed_at=_NOW,
    )


def _evidence(
    *,
    probes: tuple[LiveBlackboxProbeResult, ...] | None = None,
    backend_service_run_ref: str = "service-run.backend",
    frontend_service_run_ref: str = "service-run.frontend",
) -> LiveBlackboxIntegrationEvidence:
    return LiveBlackboxIntegrationEvidence(
        live_blackbox_evidence_id=LiveBlackboxIntegrationEvidenceRef(
            value="live-blackbox.generic-app"
        ),
        package_contract_ref=ContractId(value="package-contract-generic-app"),
        backend_command_id=ContractId(value="run-backend"),
        frontend_command_id=ContractId(value="run-frontend"),
        backend_service_run_ref=backend_service_run_ref,
        frontend_service_run_ref=frontend_service_run_ref,
        probes=probes or (_probe(),),
        generated_at=_NOW,
    )


def _package_contract() -> PackageContract:
    return PackageContract(
        package_contract_id=ContractId(value="package-contract-generic-app"),
        project_charter_ref=ContractId(value="project-charter.generic-app"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            SourceSurface(
                source_surface_ref=SourceSurfaceRef(value="tests"),
                name="Live integration tests",
                paths=("tests",),
                owned_by=OwnerSeatRef(value="owner.tests"),
                acceptance_refs=(AcceptanceRef(value="AC-GENERIC-LIVE-FRONTEND"),),
                required_tests=(RequiredTestRef(value="live-blackbox"),),
            ),
        ),
        run_commands=(
            PackageCommand(
                command_id=ContractId(value="run-backend"),
                label="Run backend",
                command=("python", "-m", "generic_backend"),
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


def _service_runs(
    *,
    frontend_command_id: str = "run-frontend",
) -> tuple[ServiceRunEvidence, ServiceRunEvidence]:
    return (
        _service_run(
            "service-run.backend",
            command_id="run-backend",
            command=("python", "-m", "generic_backend"),
            readiness_url="http://127.0.0.1:8000/ready",
            environment_overrides={"PORT": "8000"},
        ),
        _service_run(
            "service-run.frontend",
            command_id=frontend_command_id,
            command=_frontend_service_command(),
            readiness_url="http://127.0.0.1:5173/",
            environment_overrides={"FRONTEND_PORT": "5173"},
        ),
    )


def _service_run(
    service_run_ref: str,
    *,
    command_id: str,
    command: tuple[str, ...],
    readiness_url: str,
    environment_overrides: dict[str, str],
) -> ServiceRunEvidence:
    return ServiceRunEvidence(
        service_run_evidence_id=service_run_ref,
        execution_package_ref="exec.live.1",
        ticket_ref="ticket.live.1",
        command_id=command_id,
        command=command,
        cwd=".",
        process_id=4321,
        readiness_url=readiness_url,
        probe_status_code=200,
        probe_body_sha256=_HASH,
        stdout_ref=CommandOutputRef(value=f"command-output.{service_run_ref}.stdout"),
        stderr_ref=CommandOutputRef(value=f"command-output.{service_run_ref}.stderr"),
        started_at=_NOW,
        ready_at=_NOW,
        stopped_at=_NOW + timedelta(seconds=1),
        runner_ref=RunnerRef(value="runner.local-service"),
        environment_profile_ref=EnvironmentProfileRef(value="environment.local"),
        workspace_snapshot_ref=WorkspaceSnapshotRef(value="workspace-snapshot.service"),
        environment_overrides=environment_overrides,
    )


def _verifier_input(
    evidence: LiveBlackboxIntegrationEvidence,
    *,
    service_runs: tuple[ServiceRunEvidence, ...] | None = None,
) -> LiveBlackboxVerifierInput:
    return LiveBlackboxVerifierInput(
        evidence=evidence,
        package_contract=_package_contract(),
        service_runs=service_runs if service_runs is not None else _service_runs(),
    )


def test_live_blackbox_evidence_rejects_missing_probes() -> None:
    fields = _evidence().model_dump()
    fields["probes"] = ()

    with pytest.raises(ValidationError):
        LiveBlackboxIntegrationEvidence(**fields)


def test_live_blackbox_evidence_rejects_probe_without_acceptance_refs() -> None:
    fields = _probe().model_dump()
    fields["acceptance_refs"] = ()

    with pytest.raises(ValidationError):
        LiveBlackboxProbeResult(**fields)


def test_live_blackbox_rejects_failed_probe() -> None:
    evidence = _evidence(probes=(_probe(passed=False),))

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert any("probe did not pass" in blocker.message for blocker in result.blockers)


def test_live_blackbox_rejects_frontend_service_run_command_mismatch() -> None:
    evidence = _evidence()

    result = LiveBlackboxIntegrationVerifier().verify(
        _verifier_input(
            evidence,
            service_runs=_service_runs(frontend_command_id="run-backend"),
        )
    )

    assert result.success is False
    assert any("command_id" in blocker.message for blocker in result.blockers)


def test_live_blackbox_rejects_probe_url_outside_bound_service_origins() -> None:
    evidence = _evidence(
        probes=(
            _probe(
                probe_url="http://127.0.0.1:9999/some-workflow",
            ),
        )
    )

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert any("service origin" in blocker.message for blocker in result.blockers)


def test_live_blackbox_rejects_unknown_probe_service_ref() -> None:
    with pytest.raises(ValidationError, match="backend and frontend services"):
        _evidence(
            probes=(
                _probe(
                    service_run_refs=("service-run.backend", "service-run.unknown"),
                ),
            )
        )


def test_live_blackbox_rejects_unknown_probe_command_id() -> None:
    with pytest.raises(ValidationError, match="backend and frontend commands"):
        _evidence(
            probes=(
                _probe(
                    command_ids=("run-backend", "run-not-declared"),
                ),
            )
        )
