import pytest

from boardroom_os.contracts.acceptance import (
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
from boardroom_os.contracts.gates import validate_contract_gate
from boardroom_os.contracts.package import (
    IntegrationBoundary,
    PackageCommand,
    PackageContract,
    PackageProjectType,
)
from boardroom_os.contracts.project import ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import (
    AcceptanceRef,
    ContractId,
    ContractStatus,
    EvidenceObligationRef,
    SourceSurfaceRef,
)


def _charter_registry() -> ProjectCharterRegistry:
    directive = BoardDirective(
        board_directive_id=ContractId(value="directive-001"),
        source_type="natural_language",
        content_ref=ContractId(value="content-001"),
        received_at="2026-05-14T09:00:00Z",
        requester_ref=ContractId(value="human-board"),
    )
    directive_registry = DirectiveRegistry.from_directives(directive)
    charter = create_project_charter(
        registry=directive_registry,
        project_charter_id=ContractId(value="charter-001"),
        board_directive_ref=ContractId(value="directive-001"),
        project_goal="Generate a tiny book availability tracker.",
        delivery_type="generated_project_package",
        non_goals=("Do not migrate legacy runtime.",),
        constraints=("Contract first.", "Evidence first."),
        risks=("Evidence gaps block closeout.",),
        success_summary="A runnable and auditable generated project package.",
    )
    return ProjectCharterRegistry.from_charters(charter)


def _criterion(
    acceptance_ref: str = "AC-BOOK-API-001",
    *,
    blocking: bool = True,
    evidence_required: tuple[str, ...] = ("api_test_run",),
    source_surface_refs: tuple[str, ...] = ("backend-api",),
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=AcceptanceRef(value=acceptance_ref),
        statement="Books can be checked out through the backend API.",
        evidence_required=tuple(EvidenceRequirement(value=value) for value in evidence_required),
        blocking=blocking,
        source_surface_refs=tuple(SourceSurfaceRef(value=value) for value in source_surface_refs),
        verification_strategy=VerificationStrategy(value="pytest_and_source_inventory"),
    )


def _acceptance_contract(
    *,
    status: ContractStatus = ContractStatus.active(),
    criteria: tuple[AcceptanceCriterion, ...] | None = None,
):
    return create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="acceptance-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        status=status,
        criteria=criteria or (_criterion(),),
    )


def _surface(
    *,
    surface_ref: str = "backend-api",
    acceptance_refs: tuple[str, ...] = ("AC-BOOK-API-001",),
) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name="Backend API",
        paths=("backend/",),
        owned_by=OwnerSeatRef(value="worker-backend"),
        acceptance_refs=tuple(AcceptanceRef(value=value) for value in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest-backend"),),
    )


def _command(command_id: str) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id,
        command=("pytest",),
        cwd=".",
    )


def _package_contract(
    *,
    source_surfaces: tuple[SourceSurface, ...] | None = None,
) -> PackageContract:
    return PackageContract(
        package_contract_id=ContractId(value="package-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=source_surfaces or (_surface(),),
        run_commands=(_command("run-dev"),),
        test_commands=(_command("test"),),
        integration_boundaries=(IntegrationBoundary(value="http-api"),),
        docs_required=True,
        closeout_required=True,
    )


def test_contract_gate_requires_active_acceptance_contract() -> None:
    with pytest.raises(ValueError, match="active acceptance contract is required"):
        validate_contract_gate(
            acceptance_contract=_acceptance_contract(status=ContractStatus.draft()),
            package_contract=_package_contract(),
        )


def test_contract_gate_requires_package_contract() -> None:
    with pytest.raises(ValueError, match="package contract is required"):
        validate_contract_gate(
            acceptance_contract=_acceptance_contract(),
            package_contract=None,
        )


def test_contract_gate_rejects_package_acceptance_ref_outside_active_contract() -> None:
    package_contract = _package_contract(
        source_surfaces=(
            _surface(acceptance_refs=("AC-BOOK-API-001", "AC-STATIC-UNIVERSAL-999")),
        )
    )

    with pytest.raises(ValueError, match="acceptance_ref must belong to active contract"):
        validate_contract_gate(
            acceptance_contract=_acceptance_contract(),
            package_contract=package_contract,
        )


def test_contract_gate_rejects_blocking_criterion_without_blocking_obligation() -> None:
    acceptance_contract = _acceptance_contract(
        criteria=(
            _criterion(
                acceptance_ref="AC-BOOK-API-001",
                blocking=True,
                evidence_required=("api_test_run",),
                source_surface_refs=("backend-api",),
            ),
        )
    )

    with pytest.raises(ValueError, match="blocking criterion requires blocking obligation"):
        validate_contract_gate(
            acceptance_contract=acceptance_contract,
            package_contract=_package_contract(),
            evidence_obligations=(),
        )


def test_contract_gate_rejects_explicit_obligations_missing_required_evidence() -> None:
    acceptance_contract = _acceptance_contract(
        criteria=(
            _criterion(
                acceptance_ref="AC-BOOK-API-001",
                blocking=True,
                evidence_required=("api_test_run", "backend_source_inventory"),
                source_surface_refs=("backend-api",),
            ),
        )
    )
    only_one_obligation = EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="obl-AC-BOOK-API-001-api_test_run"),
        acceptance_refs=(AcceptanceRef(value="AC-BOOK-API-001"),),
        source_surface_refs=(SourceSurfaceRef(value="backend-api"),),
        required_artifact_type=RequiredArtifactType(value="api_test_run"),
        required_verifier=RequiredVerifier(value="pytest_and_source_inventory"),
        blocking=True,
    )

    with pytest.raises(ValueError, match="evidence obligations must match active contract"):
        validate_contract_gate(
            acceptance_contract=acceptance_contract,
            package_contract=_package_contract(),
            evidence_obligations=(only_one_obligation,),
        )


def test_contract_gate_rejects_criterion_source_surface_missing_from_package_contract() -> None:
    acceptance_contract = _acceptance_contract(
        criteria=(
            _criterion(
                acceptance_ref="AC-BOOK-API-001",
                blocking=True,
                evidence_required=("api_test_run",),
                source_surface_refs=("backend-api", "persistence"),
            ),
        )
    )

    with pytest.raises(ValueError, match="source_surface_ref must belong to package contract"):
        validate_contract_gate(
            acceptance_contract=acceptance_contract,
            package_contract=_package_contract(),
        )
