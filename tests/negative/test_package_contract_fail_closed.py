import pytest
from pydantic import ValidationError

from boardroom_os.contracts.package import (
    IntegrationBoundary,
    PackageCommand,
    PackageContract,
    PackageProjectType,
)
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, SourceSurfaceRef


def _surface(surface_ref: str = "backend-api") -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name="Backend API",
        paths=("backend/",),
        owned_by=OwnerSeatRef(value="worker-backend"),
        acceptance_refs=(AcceptanceRef(value="AC-BOOK-API-001"),),
        required_tests=(RequiredTestRef(value="pytest-backend"),),
    )


def _command(command_id: str, command: tuple[str, ...]) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id,
        command=command,
        cwd=".",
    )


def test_source_surface_requires_acceptance_refs() -> None:
    with pytest.raises(ValidationError, match="acceptance refs must not be empty"):
        SourceSurface(
            source_surface_ref=SourceSurfaceRef(value="backend-api"),
            name="Backend API",
            paths=("backend/",),
            owned_by=OwnerSeatRef(value="worker-backend"),
            acceptance_refs=(),
            required_tests=(RequiredTestRef(value="pytest-backend"),),
        )


def test_source_surface_requires_paths() -> None:
    with pytest.raises(ValidationError, match="paths must not be empty"):
        SourceSurface(
            source_surface_ref=SourceSurfaceRef(value="backend-api"),
            name="Backend API",
            paths=(),
            owned_by=OwnerSeatRef(value="worker-backend"),
            acceptance_refs=(AcceptanceRef(value="AC-BOOK-API-001"),),
            required_tests=(RequiredTestRef(value="pytest-backend"),),
        )


def test_package_contract_requires_package_root() -> None:
    with pytest.raises(ValidationError, match="package_root"):
        PackageContract(
            package_contract_id=ContractId(value="package-contract-001"),
            project_charter_ref=ContractId(value="charter-001"),
            project_type=PackageProjectType.SOFTWARE,
            source_surfaces=(_surface(),),
            run_commands=(_command("run-dev", ("python", "-m", "uvicorn", "app:app")),),
            test_commands=(_command("test", ("pytest",)),),
            integration_boundaries=(IntegrationBoundary(value="http-api"),),
            docs_required=True,
            closeout_required=True,
        )


def test_package_contract_requires_source_surfaces() -> None:
    with pytest.raises(ValidationError, match="source surfaces must not be empty"):
        PackageContract(
            package_contract_id=ContractId(value="package-contract-001"),
            project_charter_ref=ContractId(value="charter-001"),
            package_root="10-project",
            project_type=PackageProjectType.SOFTWARE,
            source_surfaces=(),
            run_commands=(_command("run-dev", ("python", "-m", "uvicorn", "app:app")),),
            test_commands=(_command("test", ("pytest",)),),
            integration_boundaries=(IntegrationBoundary(value="http-api"),),
            docs_required=True,
            closeout_required=True,
        )


def test_package_contract_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PackageContract(
            package_contract_id=ContractId(value="package-contract-001"),
            project_charter_ref=ContractId(value="charter-001"),
            package_root="10-project",
            project_type=PackageProjectType.SOFTWARE,
            source_surfaces=(_surface(),),
            run_commands=(_command("run-dev", ("python", "-m", "uvicorn", "app:app")),),
            test_commands=(_command("test", ("pytest",)),),
            integration_boundaries=(IntegrationBoundary(value="http-api"),),
            docs_required=True,
            closeout_required=True,
            unknown_field=True,
        )


def test_package_command_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        PackageCommand(
            command_id=ContractId(value="run-dev"),
            label="run-dev",
            command=("python", "-m", "uvicorn", "app:app"),
            cwd=".",
            unknown_field=True,
        )


def test_package_contract_requires_strict_docs_required_bool() -> None:
    with pytest.raises(ValidationError):
        PackageContract(
            package_contract_id=ContractId(value="package-contract-001"),
            project_charter_ref=ContractId(value="charter-001"),
            package_root="10-project",
            project_type=PackageProjectType.SOFTWARE,
            source_surfaces=(_surface(),),
            run_commands=(_command("run-dev", ("python", "-m", "uvicorn", "app:app")),),
            test_commands=(_command("test", ("pytest",)),),
            integration_boundaries=(IntegrationBoundary(value="http-api"),),
            docs_required="false",
            closeout_required=True,
        )


def test_package_contract_requires_strict_closeout_required_bool() -> None:
    with pytest.raises(ValidationError):
        PackageContract(
            package_contract_id=ContractId(value="package-contract-001"),
            project_charter_ref=ContractId(value="charter-001"),
            package_root="10-project",
            project_type=PackageProjectType.SOFTWARE,
            source_surfaces=(_surface(),),
            run_commands=(_command("run-dev", ("python", "-m", "uvicorn", "app:app")),),
            test_commands=(_command("test", ("pytest",)),),
            integration_boundaries=(IntegrationBoundary(value="http-api"),),
            docs_required=True,
            closeout_required=1,
        )


@pytest.mark.parametrize(
    "project_type",
    (PackageProjectType.SOFTWARE, PackageProjectType.MIXED),
)
def test_runnable_package_contract_requires_run_commands(
    project_type: PackageProjectType,
) -> None:
    with pytest.raises(ValidationError, match="software and mixed packages require run commands"):
        PackageContract(
            package_contract_id=ContractId(value="package-contract-001"),
            project_charter_ref=ContractId(value="charter-001"),
            package_root="10-project",
            project_type=project_type,
            source_surfaces=(_surface(),),
            run_commands=(),
            test_commands=(_command("test", ("pytest",)),),
            integration_boundaries=(IntegrationBoundary(value="http-api"),),
            docs_required=True,
            closeout_required=True,
        )


@pytest.mark.parametrize(
    "project_type",
    (PackageProjectType.SOFTWARE, PackageProjectType.MIXED),
)
def test_runnable_package_contract_requires_test_commands(
    project_type: PackageProjectType,
) -> None:
    with pytest.raises(ValidationError, match="software and mixed packages require test commands"):
        PackageContract(
            package_contract_id=ContractId(value="package-contract-001"),
            project_charter_ref=ContractId(value="charter-001"),
            package_root="10-project",
            project_type=project_type,
            source_surfaces=(_surface(),),
            run_commands=(_command("run-dev", ("python", "-m", "uvicorn", "app:app")),),
            test_commands=(),
            integration_boundaries=(IntegrationBoundary(value="http-api"),),
            docs_required=True,
            closeout_required=True,
        )
