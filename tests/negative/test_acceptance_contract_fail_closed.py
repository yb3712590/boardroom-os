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
from boardroom_os.contracts.project import ProjectCharter, ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.types import AcceptanceRef, ContractId, ContractStatus, SourceSurfaceRef


def _registered_charter() -> ProjectCharterRegistry:
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
        constraints=("Contract first.",),
        risks=("Evidence gaps block closeout.",),
        success_summary="A runnable and auditable generated project package.",
    )
    return ProjectCharterRegistry.from_charters(charter)


def _criterion(*, blocking: bool = True) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=AcceptanceRef(value="AC-BOOK-API-001"),
        statement="Books can be checked out through the backend API.",
        evidence_required=(EvidenceRequirement(value="api_test_run"),),
        blocking=blocking,
        source_surface_refs=(SourceSurfaceRef(value="backend-api"),),
        verification_strategy=VerificationStrategy(value="pytest_api"),
    )


def test_acceptance_contract_rejects_empty_criteria() -> None:
    with pytest.raises(ValidationError, match="criteria must not be empty"):
        create_acceptance_contract(
            registry=_registered_charter(),
            acceptance_contract_id=ContractId(value="acceptance-contract-001"),
            project_charter_ref=ContractId(value="charter-001"),
            status=ContractStatus.active(),
            criteria=(),
        )


def test_acceptance_contract_requires_at_least_one_blocking_criterion() -> None:
    with pytest.raises(ValidationError, match="at least one blocking criterion is required"):
        create_acceptance_contract(
            registry=_registered_charter(),
            acceptance_contract_id=ContractId(value="acceptance-contract-001"),
            project_charter_ref=ContractId(value="charter-001"),
            status=ContractStatus.active(),
            criteria=(_criterion(blocking=False),),
        )


def test_acceptance_criterion_requires_evidence_required() -> None:
    with pytest.raises(ValidationError):
        AcceptanceCriterion(
            acceptance_ref=AcceptanceRef(value="AC-BOOK-API-001"),
            statement="Books can be checked out through the backend API.",
            evidence_required=(),
            blocking=True,
            source_surface_refs=(SourceSurfaceRef(value="backend-api"),),
            verification_strategy=VerificationStrategy(value="pytest_api"),
        )


def test_acceptance_criterion_requires_source_surface_refs() -> None:
    with pytest.raises(ValidationError):
        AcceptanceCriterion(
            acceptance_ref=AcceptanceRef(value="AC-BOOK-API-001"),
            statement="Books can be checked out through the backend API.",
            evidence_required=(EvidenceRequirement(value="api_test_run"),),
            blocking=True,
            source_surface_refs=(),
            verification_strategy=VerificationStrategy(value="pytest_api"),
        )


def test_acceptance_contract_direct_constructor_requires_project_charter_registry() -> None:
    with pytest.raises(ValidationError, match="project charter registry is required"):
        AcceptanceContract(
            acceptance_contract_id=ContractId(value="acceptance-contract-001"),
            project_charter_ref=ContractId(value="charter-001"),
            status=ContractStatus.active(),
            criteria=(_criterion(),),
        )


def test_acceptance_contract_rejects_unknown_project_charter_ref() -> None:
    with pytest.raises(ValidationError, match="project charter ref must exist"):
        create_acceptance_contract(
            registry=ProjectCharterRegistry(charters=()),
            acceptance_contract_id=ContractId(value="acceptance-contract-001"),
            project_charter_ref=ContractId(value="charter-missing"),
            status=ContractStatus.active(),
            criteria=(_criterion(),),
        )


def test_acceptance_contract_rejects_charter_without_board_directive_ref() -> None:
    with pytest.raises(ValidationError, match="board_directive_ref"):
        ProjectCharter(
            project_charter_id=ContractId(value="charter-001"),
            project_goal="Generate a tiny book availability tracker.",
            delivery_type="generated_project_package",
            non_goals=("Do not migrate legacy runtime.",),
            constraints=("Contract first.",),
            risks=("Evidence gaps block closeout.",),
            success_summary="A runnable and auditable generated project package.",
        )
