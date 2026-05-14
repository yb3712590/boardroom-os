from boardroom_os.contracts.acceptance import (
    AcceptanceContract,
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
    create_acceptance_contract,
)
from boardroom_os.contracts.directive import BoardDirective, DirectiveRegistry
from boardroom_os.contracts.project import ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.types import AcceptanceRef, ContractId, ContractStatus, SourceSurfaceRef


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
    acceptance_ref: str,
    *,
    statement: str,
    blocking: bool,
    evidence_required: tuple[str, ...],
    source_surface_refs: tuple[str, ...],
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=AcceptanceRef(value=acceptance_ref),
        statement=statement,
        evidence_required=tuple(
            EvidenceRequirement(value=evidence_ref)
            for evidence_ref in evidence_required
        ),
        blocking=blocking,
        source_surface_refs=tuple(
            SourceSurfaceRef(value=surface_ref)
            for surface_ref in source_surface_refs
        ),
        verification_strategy=VerificationStrategy(value="pytest_and_source_inventory"),
    )


def test_acceptance_contract_binds_dynamic_criteria_to_project_charter() -> None:
    contract = create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="acceptance-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        status=ContractStatus.active(),
        criteria=(
            _criterion(
                "AC-BOOK-API-001",
                statement="Books can be checked out through the backend API.",
                blocking=True,
                evidence_required=("api_test_run", "backend_source_inventory"),
                source_surface_refs=("backend-api",),
            ),
            _criterion(
                "AC-BOOK-DOCS-001",
                statement="The generated package documents how to run the service.",
                blocking=False,
                evidence_required=("docs_source_inventory",),
                source_surface_refs=("docs",),
            ),
        ),
    )

    assert isinstance(contract, AcceptanceContract)
    assert contract.project_charter_ref.value == "charter-001"
    assert [criterion.acceptance_ref.value for criterion in contract.criteria] == [
        "AC-BOOK-API-001",
        "AC-BOOK-DOCS-001",
    ]
    assert contract.model_dump() == {
        "acceptance_contract_id": {"value": "acceptance-contract-001"},
        "project_charter_ref": {"value": "charter-001"},
        "status": {"value": "active"},
        "criteria": [
            {
                "acceptance_ref": {"value": "AC-BOOK-API-001"},
                "statement": "Books can be checked out through the backend API.",
                "evidence_required": [
                    {"value": "api_test_run"},
                    {"value": "backend_source_inventory"},
                ],
                "blocking": True,
                "source_surface_refs": [{"value": "backend-api"}],
                "verification_strategy": {"value": "pytest_and_source_inventory"},
            },
            {
                "acceptance_ref": {"value": "AC-BOOK-DOCS-001"},
                "statement": "The generated package documents how to run the service.",
                "evidence_required": [{"value": "docs_source_inventory"}],
                "blocking": False,
                "source_surface_refs": [{"value": "docs"}],
                "verification_strategy": {"value": "pytest_and_source_inventory"},
            },
        ],
    }


def test_active_acceptance_contract_returns_only_blocking_criteria() -> None:
    contract = create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="acceptance-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        status=ContractStatus.active(),
        criteria=(
            _criterion(
                "AC-BOOK-API-001",
                statement="Books can be checked out through the backend API.",
                blocking=True,
                evidence_required=("api_test_run",),
                source_surface_refs=("backend-api",),
            ),
            _criterion(
                "AC-BOOK-DOCS-001",
                statement="The generated package documents how to run the service.",
                blocking=False,
                evidence_required=("docs_source_inventory",),
                source_surface_refs=("docs",),
            ),
        ),
    )

    assert [criterion.acceptance_ref.value for criterion in contract.blocking_criteria()] == [
        "AC-BOOK-API-001"
    ]


def test_draft_acceptance_contract_returns_no_blocking_criteria_for_gate_consumers() -> None:
    contract = create_acceptance_contract(
        registry=_charter_registry(),
        acceptance_contract_id=ContractId(value="acceptance-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        status=ContractStatus.draft(),
        criteria=(
            _criterion(
                "AC-BOOK-API-001",
                statement="Books can be checked out through the backend API.",
                blocking=True,
                evidence_required=("api_test_run",),
                source_surface_refs=("backend-api",),
            ),
        ),
    )

    assert contract.blocking_criteria() == ()


def test_contract_package_exports_acceptance_contract_types() -> None:
    from boardroom_os.contracts import (
        AcceptanceContract,
        AcceptanceCriterion,
        EvidenceRequirement,
        ProjectCharterRegistry,
        VerificationStrategy,
        create_acceptance_contract,
    )

    assert AcceptanceContract.__name__ == "AcceptanceContract"
    assert AcceptanceCriterion.__name__ == "AcceptanceCriterion"
    assert EvidenceRequirement.__name__ == "EvidenceRequirement"
    assert ProjectCharterRegistry.__name__ == "ProjectCharterRegistry"
    assert VerificationStrategy.__name__ == "VerificationStrategy"
    assert create_acceptance_contract.__name__ == "create_acceptance_contract"
