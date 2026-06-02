from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from boardroom_os.contracts.package import IntegrationBoundary, PackageCommand, PackageContract, PackageProjectType
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, SourceSurfaceRef
from boardroom_os.evidence.live_blackbox import (
    BackendCrudProbeResult,
    FrontendLiveProbeResult,
    LiveBlackboxIntegrationEvidence,
    LiveBlackboxIntegrationEvidenceRef,
    LiveBlackboxIntegrationVerifier,
    LiveBlackboxVerifierInput,
    SQLitePersistenceProbeResult,
)
from boardroom_os.evidence.service_run import ServiceReadinessUrl, ServiceRunEvidence
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


def _backend_probe(
    *,
    backend_url: str = "http://127.0.0.1:8000/health",
    checkout_seen: bool = True,
    return_seen: bool = True,
    delete_seen: bool = True,
) -> BackendCrudProbeResult:
    return BackendCrudProbeResult(
        backend_url=ServiceReadinessUrl(value=backend_url),
        created_book_id=1,
        create_status=201,
        list_status=200,
        checkout_status=200 if checkout_seen else 404,
        checkout_state="CHECKED_OUT" if checkout_seen else "IN_LIBRARY",
        return_status=200 if return_seen else 404,
        return_state="IN_LIBRARY",
        delete_status=200 if delete_seen else 404,
        delete_confirmed=delete_seen,
        probed_at=_NOW,
    )


def _sqlite_probe(*, via_http: bool = True) -> SQLitePersistenceProbeResult:
    return SQLitePersistenceProbeResult(
        db_path=Path("books.sqlite3"),
        table_names=("books",),
        observed_states=("CHECKED_OUT", "IN_LIBRARY"),
        deleted_book_absent=True,
        source="http_workflow" if via_http else "function_unit_test",
        probed_at=_NOW,
    )


def _frontend_probe(
    *,
    fake_fetch_only: bool = False,
    fetched_paths: tuple[str, ...] = ("/health", "/books", "/books/1"),
    fetched_methods: tuple[str, ...] = ("GET", "GET", "DELETE"),
) -> FrontendLiveProbeResult:
    return FrontendLiveProbeResult(
        frontend_url=ServiceReadinessUrl(value="http://127.0.0.1:5173/index.html"),
        backend_url=ServiceReadinessUrl(value="http://127.0.0.1:8000/health"),
        fetched_paths=fetched_paths,
        fetched_methods=fetched_methods,
        used_fake_fetch=fake_fetch_only,
        response_body_sha256=_HASH,
        probed_at=_NOW,
    )


def _evidence(
    *,
    backend_probe: BackendCrudProbeResult | None = None,
    sqlite_probe: SQLitePersistenceProbeResult | None = None,
    frontend_probe: FrontendLiveProbeResult | None = None,
) -> LiveBlackboxIntegrationEvidence:
    return LiveBlackboxIntegrationEvidence(
        live_blackbox_evidence_id=LiveBlackboxIntegrationEvidenceRef(
            value="live-blackbox.tiny-fullstack"
        ),
        package_contract_ref=ContractId(value="package-contract-tiny-fullstack"),
        backend_command_id=ContractId(value="run-backend"),
        frontend_command_id=ContractId(value="run-frontend"),
        backend_service_run_ref="service-run.backend",
        frontend_service_run_ref="service-run.frontend",
        backend_probe=backend_probe or _backend_probe(),
        sqlite_probe=sqlite_probe or _sqlite_probe(),
        frontend_probe=frontend_probe or _frontend_probe(),
        generated_at=_NOW,
    )


def _package_contract() -> PackageContract:
    return PackageContract(
        package_contract_id=ContractId(value="package-contract-tiny-fullstack"),
        project_charter_ref=ContractId(value="project-charter.tiny-fullstack"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            SourceSurface(
                source_surface_ref=SourceSurfaceRef(value="tests"),
                name="Live integration tests",
                paths=("tests",),
                owned_by=OwnerSeatRef(value="owner.tests"),
                acceptance_refs=(AcceptanceRef(value="AC-TINY-BACKEND-HTTP-CRUD"),),
                required_tests=(RequiredTestRef(value="live-blackbox"),),
            ),
        ),
        run_commands=(
            PackageCommand(
                command_id=ContractId(value="run-backend"),
                label="Run backend",
                command=("python", "-m", "backend.app"),
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
    backend_db_path: str | None = "books.sqlite3",
) -> tuple[ServiceRunEvidence, ServiceRunEvidence]:
    backend_environment = {"PORT": "8000"}
    if backend_db_path is not None:
        backend_environment["BOOKS_DB_PATH"] = backend_db_path
    return (
        _service_run(
            "service-run.backend",
            command_id="run-backend",
            command=("python", "-m", "backend.app"),
            cwd=".",
            readiness_url="http://127.0.0.1:8000/health",
            environment_overrides=backend_environment,
        ),
        _service_run(
            "service-run.frontend",
            command_id=frontend_command_id,
            command=_frontend_service_command(),
            cwd=".",
            readiness_url="http://127.0.0.1:5173/index.html",
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
) -> ServiceRunEvidence:
    return ServiceRunEvidence(
        service_run_evidence_id=service_run_ref,
        execution_package_ref="exec.live.1",
        ticket_ref="ticket.live.1",
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


@pytest.mark.parametrize(
    ("field", "probe"),
    [
        ("backend_probe", None),
        ("sqlite_probe", None),
        ("frontend_probe", None),
    ],
)
def test_live_blackbox_evidence_rejects_missing_probe(field: str, probe: object) -> None:
    fields = _evidence().model_dump()
    fields[field] = probe

    with pytest.raises(ValidationError):
        LiveBlackboxIntegrationEvidence(**fields)


def test_live_blackbox_rejects_backend_missing_delete() -> None:
    evidence = _evidence(backend_probe=_backend_probe(delete_seen=False))

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert "delete" in result.blockers[0].message


def test_live_blackbox_rejects_backend_missing_checkout_or_return() -> None:
    evidence = _evidence(backend_probe=_backend_probe(checkout_seen=False, return_seen=False))

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert any("checkout" in blocker.message for blocker in result.blockers)
    assert any("return" in blocker.message for blocker in result.blockers)


def test_live_blackbox_rejects_sqlite_function_unit_test_only() -> None:
    evidence = _evidence(sqlite_probe=_sqlite_probe(via_http=False))

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert any("HTTP workflow" in blocker.message for blocker in result.blockers)


def test_live_blackbox_rejects_fake_fetch_only_frontend() -> None:
    evidence = _evidence(frontend_probe=_frontend_probe(fake_fetch_only=True))

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert any("fakeFetch" in blocker.message for blocker in result.blockers)


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


def test_live_blackbox_rejects_frontend_probe_url_not_bound_to_frontend_service_run() -> None:
    evidence = _evidence(
        frontend_probe=_frontend_probe().model_copy(
            update={
                "frontend_url": ServiceReadinessUrl(value="http://127.0.0.1:9999/index.html"),
            }
        )
    )

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert any("frontend_url" in blocker.message for blocker in result.blockers)


def test_live_blackbox_rejects_backend_probe_url_not_bound_to_backend_service_run() -> None:
    evidence = _evidence(
        frontend_probe=_frontend_probe().model_copy(
            update={
                "backend_url": ServiceReadinessUrl(value="http://127.0.0.1:9999/health"),
            }
        )
    )

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert any("backend_url" in blocker.message for blocker in result.blockers)


def test_live_blackbox_rejects_backend_crud_probe_url_not_bound_to_backend_service_run() -> None:
    evidence = _evidence(
        backend_probe=_backend_probe(backend_url="http://127.0.0.1:9999/health")
    )

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert any("backend_probe.backend_url" in blocker.message for blocker in result.blockers)


def test_live_blackbox_rejects_sqlite_probe_db_path_not_bound_to_backend_service_run() -> None:
    evidence = _evidence(
        sqlite_probe=_sqlite_probe().model_copy(
            update={"db_path": Path("other.sqlite3")}
        )
    )

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert any("BOOKS_DB_PATH" in blocker.message for blocker in result.blockers)


def test_live_blackbox_rejects_frontend_probe_without_delete_request_trace() -> None:
    evidence = _evidence(
        frontend_probe=_frontend_probe(
            fetched_paths=("/health", "/books"),
            fetched_methods=("GET", "GET"),
        )
    )

    result = LiveBlackboxIntegrationVerifier().verify(_verifier_input(evidence))

    assert result.success is False
    assert any("DELETE" in blocker.message for blocker in result.blockers)
