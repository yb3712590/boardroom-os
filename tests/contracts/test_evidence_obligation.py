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
from boardroom_os.contracts.gates import compile_evidence_obligations, validate_contract_gate
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


def test_evidence_obligation_serializes_required_contract_refs() -> None:
    obligation = EvidenceObligation(
        evidence_obligation_id=EvidenceObligationRef(value="obl-AC-BOOK-API-001-api_test_run"),
        acceptance_refs=(AcceptanceRef(value="AC-BOOK-API-001"),),
        source_surface_refs=(SourceSurfaceRef(value="backend-api"),),
        required_artifact_type=RequiredArtifactType(value="api_test_run"),
        required_verifier=RequiredVerifier(value="pytest_and_source_inventory"),
        blocking=True,
    )

    assert obligation.model_dump() == {
        "evidence_obligation_id": {"value": "obl-AC-BOOK-API-001-api_test_run"},
        "acceptance_refs": [{"value": "AC-BOOK-API-001"}],
        "source_surface_refs": [{"value": "backend-api"}],
        "required_artifact_type": {"value": "api_test_run"},
        "required_verifier": {"value": "pytest_and_source_inventory"},
        "blocking": True,
    }


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
        evidence_required=tuple(EvidenceRequirement(value=value) for value in evidence_required),
        blocking=blocking,
        source_surface_refs=tuple(SourceSurfaceRef(value=value) for value in source_surface_refs),
        verification_strategy=VerificationStrategy(value="pytest_and_source_inventory"),
    )


def _surface(
    *,
    surface_ref: str,
    acceptance_refs: tuple[str, ...],
) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name=surface_ref,
        paths=(f"{surface_ref}/",),
        owned_by=OwnerSeatRef(value="worker-fullstack"),
        acceptance_refs=tuple(AcceptanceRef(value=value) for value in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest"),),
    )


def _command(command_id: str) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id,
        command=("pytest",),
        cwd=".",
    )


def _package_contract() -> PackageContract:
    return PackageContract(
        package_contract_id=ContractId(value="package-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface(surface_ref="backend-api", acceptance_refs=("AC-BOOK-API-001",)),
            _surface(surface_ref="tests", acceptance_refs=("AC-BOOK-API-001", "AC-BOOK-RUN-001")),
            _surface(surface_ref="run-manifest", acceptance_refs=("AC-BOOK-RUN-001",)),
            _surface(surface_ref="docs", acceptance_refs=("AC-BOOK-DOCS-001",)),
        ),
        run_commands=(_command("run-dev"),),
        test_commands=(_command("test"),),
        integration_boundaries=(IntegrationBoundary(value="http-api"),),
        docs_required=True,
        closeout_required=True,
    )


def _acceptance_contract():
    return create_acceptance_contract(
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
                source_surface_refs=("backend-api", "tests"),
            ),
            _criterion(
                "AC-BOOK-RUN-001",
                statement="The package has declared run commands.",
                blocking=True,
                evidence_required=("run_manifest",),
                source_surface_refs=("run-manifest",),
            ),
            _criterion(
                "AC-BOOK-DOCS-001",
                statement="The package documents how to run the service.",
                blocking=False,
                evidence_required=("docs_source_inventory",),
                source_surface_refs=("docs",),
            ),
        ),
    )


def test_compile_evidence_obligations_expands_blocking_criteria_by_required_evidence() -> None:
    obligations = compile_evidence_obligations(_acceptance_contract())

    assert [obligation.evidence_obligation_id.value for obligation in obligations] == [
        "obl-AC-BOOK-API-001-api_test_run",
        "obl-AC-BOOK-API-001-backend_source_inventory",
        "obl-AC-BOOK-RUN-001-run_manifest",
    ]
    assert [obligation.required_artifact_type.value for obligation in obligations] == [
        "api_test_run",
        "backend_source_inventory",
        "run_manifest",
    ]
    assert all(obligation.blocking for obligation in obligations)
    assert [ref.value for ref in obligations[0].source_surface_refs] == ["backend-api", "tests"]


def test_validate_contract_gate_returns_ticket_ready_contract_refs_and_obligations() -> None:
    result = validate_contract_gate(
        acceptance_contract=_acceptance_contract(),
        package_contract=_package_contract(),
    )

    assert result.acceptance_contract_ref.value == "acceptance-contract-001"
    assert result.package_contract_ref.value == "package-contract-001"
    assert [ref.value for ref in result.acceptance_refs] == [
        "AC-BOOK-API-001",
        "AC-BOOK-RUN-001",
    ]
    assert [ref.value for ref in result.source_surface_refs] == [
        "backend-api",
        "tests",
        "run-manifest",
    ]
    assert [obligation.evidence_obligation_id.value for obligation in result.evidence_obligations] == [
        "obl-AC-BOOK-API-001-api_test_run",
        "obl-AC-BOOK-API-001-backend_source_inventory",
        "obl-AC-BOOK-RUN-001-run_manifest",
    ]


def test_contract_package_exports_evidence_obligation_and_gate_types() -> None:
    from boardroom_os.contracts import (
        ContractGateResult,
        EvidenceObligation,
        RequiredArtifactType,
        RequiredVerifier,
        compile_evidence_obligations,
        validate_contract_gate,
    )

    assert ContractGateResult.__name__ == "ContractGateResult"
    assert EvidenceObligation.__name__ == "EvidenceObligation"
    assert RequiredArtifactType.__name__ == "RequiredArtifactType"
    assert RequiredVerifier.__name__ == "RequiredVerifier"
    assert compile_evidence_obligations.__name__ == "compile_evidence_obligations"
    assert validate_contract_gate.__name__ == "validate_contract_gate"
