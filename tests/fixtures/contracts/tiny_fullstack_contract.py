from dataclasses import dataclass
from typing import Mapping

from boardroom_os.contracts.acceptance import (
    AcceptanceContract,
    AcceptanceCriterion,
    EvidenceRequirement,
    VerificationStrategy,
    create_acceptance_contract,
)
from boardroom_os.contracts.directive import BoardDirective, DirectiveRegistry
from boardroom_os.contracts.gates import ContractGateResult, validate_contract_gate
from boardroom_os.contracts.methodology import (
    DocumentationDensity,
    MethodologyProfile,
    MethodologyProfileRegistry,
    MethodologyTemplateKind,
    default_documentation_obligations_for,
    docs_template_key_for,
)
from boardroom_os.contracts.package import (
    IntegrationBoundary,
    PackageCommand,
    PackageContract,
    PackageProjectType,
    create_package_contract,
)
from boardroom_os.contracts.project import ProjectCharter, ProjectCharterRegistry, create_project_charter
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, ContractStatus, SourceSurfaceRef

TINY_FULLSTACK_AC_V2_BINDINGS = {
    "AC-TINY-API-BOOK-CREATE": ("AC-V2-CONTRACT-001", "AC-V2-PACKAGE-002"),
    "AC-TINY-API-BOOK-LIST": ("AC-V2-CONTRACT-001", "AC-V2-PACKAGE-002"),
    "AC-TINY-API-CHECKOUT-RETURN": ("AC-V2-CONTRACT-001", "AC-V2-PACKAGE-002"),
    "AC-TINY-PERSISTENCE-SQLITE": ("AC-V2-CONTRACT-001", "AC-V2-EVIDENCE-003"),
    "AC-TINY-UI-FETCH-BACKEND": ("AC-V2-CONTRACT-001", "AC-V2-PACKAGE-001"),
    "AC-TINY-RUN-TEST-COMMANDS": ("AC-V2-EVIDENCE-001", "AC-V2-PACKAGE-002"),
}

_ALLOWED_AC_V2_REFS = {
    "AC-V2-CONTRACT-001",
    "AC-V2-CONTRACT-002",
    "AC-V2-CONTRACT-003",
    "AC-V2-EVIDENCE-001",
    "AC-V2-EVIDENCE-003",
    "AC-V2-EXECUTION-003",
    "AC-V2-PACKAGE-001",
    "AC-V2-PACKAGE-002",
}
_FALLBACK_FORBIDDEN_ACCEPTANCE_REF = "AC-TINY-EVIDENCE-NO-FALLBACK"


@dataclass(frozen=True)
class TinyFullstackContractFixture:
    board_directive: BoardDirective
    project_charter: ProjectCharter
    methodology_profile: MethodologyProfile
    acceptance_contract: AcceptanceContract
    package_contract: PackageContract
    contract_gate: ContractGateResult
    ac_v2_bindings: Mapping[str, tuple[str, ...]]


def build_tiny_fullstack_contract_fixture() -> TinyFullstackContractFixture:
    board_directive = BoardDirective(
        board_directive_id=ContractId(value="directive-tiny-fullstack"),
        source_type="natural_language",
        content_ref=ContractId(value="doc-04-implementation-proving-scenario-tiny-fullstack"),
        received_at="2026-05-15T09:00:00Z",
        requester_ref=ContractId(value="human-board"),
    )
    directive_registry = DirectiveRegistry.from_directives(board_directive)
    project_charter = create_project_charter(
        registry=directive_registry,
        project_charter_id=ContractId(value="charter-tiny-fullstack"),
        board_directive_ref=board_directive.board_directive_id,
        project_goal="Generate a tiny anonymous book availability tracker package.",
        delivery_type="generated_project_package",
        non_goals=(
            "No authentication.",
            "No multi-user history.",
            "No cloud deployment.",
            "No styling polish.",
        ),
        constraints=(
            "Frontend calls backend API.",
            "SQLite persistence is required.",
            "Local run and test commands are required.",
        ),
        risks=(
            "Static placeholder frontend would hide missing integration.",
            "Synthetic test output would hide missing command evidence.",
        ),
        success_summary="Runnable generated project package with complete verified evidence and audit material.",
    )
    methodology_profile = _methodology_profile(project_charter.project_charter_id)
    acceptance_contract = _acceptance_contract(project_charter)
    package_contract = _package_contract(
        project_charter=project_charter,
        methodology_profile=methodology_profile,
    )
    contract_gate = validate_contract_gate(
        acceptance_contract=acceptance_contract,
        package_contract=package_contract,
    )
    validate_tiny_fullstack_ac_v2_bindings(
        acceptance_contract=acceptance_contract,
        ac_v2_bindings=TINY_FULLSTACK_AC_V2_BINDINGS,
    )

    return TinyFullstackContractFixture(
        board_directive=board_directive,
        project_charter=project_charter,
        methodology_profile=methodology_profile,
        acceptance_contract=acceptance_contract,
        package_contract=package_contract,
        contract_gate=contract_gate,
        ac_v2_bindings=TINY_FULLSTACK_AC_V2_BINDINGS,
    )


def validate_tiny_fullstack_ac_v2_bindings(
    *,
    acceptance_contract: AcceptanceContract,
    ac_v2_bindings: Mapping[str, tuple[str, ...]],
) -> None:
    blocking_acceptance_refs = {
        criterion.acceptance_ref.value
        for criterion in acceptance_contract.blocking_criteria()
    }
    missing_refs = blocking_acceptance_refs - set(ac_v2_bindings)
    if missing_refs:
        raise ValueError("AC-V2 binding is required for every blocking acceptance_ref")

    for acceptance_ref, ac_v2_refs in ac_v2_bindings.items():
        if acceptance_ref == _FALLBACK_FORBIDDEN_ACCEPTANCE_REF:
            raise ValueError("fallback cannot satisfy implementation evidence")
        if acceptance_ref not in blocking_acceptance_refs:
            raise ValueError("AC-V2 binding must reference an active blocking acceptance_ref")
        if not ac_v2_refs:
            raise ValueError("AC-V2 binding is required for every blocking acceptance_ref")
        unknown_refs = set(ac_v2_refs) - _ALLOWED_AC_V2_REFS
        if unknown_refs:
            raise ValueError("unknown AC-V2 binding")


def _methodology_profile(project_charter_ref: ContractId) -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile-tiny-fullstack"),
        project_charter_ref=project_charter_ref,
        template_kind=template_kind,
        documentation_density=DocumentationDensity.HEAVY,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _acceptance_contract(project_charter: ProjectCharter) -> AcceptanceContract:
    charter_registry = ProjectCharterRegistry.from_charters(project_charter)
    return create_acceptance_contract(
        registry=charter_registry,
        acceptance_contract_id=ContractId(value="acceptance-contract-tiny-fullstack"),
        project_charter_ref=project_charter.project_charter_id,
        status=ContractStatus.active(),
        criteria=(
            _criterion(
                acceptance_ref="AC-TINY-API-BOOK-CREATE",
                statement="Backend API can create books.",
                evidence_required=("api_test_run", "backend_source_inventory"),
                source_surface_refs=("backend-api", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-API-BOOK-LIST",
                statement="Backend API can list books.",
                evidence_required=("api_test_run", "backend_source_inventory"),
                source_surface_refs=("backend-api", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-API-CHECKOUT-RETURN",
                statement="Backend API supports checkout and return state transitions.",
                evidence_required=("api_test_run", "backend_source_inventory"),
                source_surface_refs=("backend-api", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-PERSISTENCE-SQLITE",
                statement="SQLite persistence records book state.",
                evidence_required=("sqlite_persistence_evidence", "backend_source_inventory"),
                source_surface_refs=("persistence", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-UI-FETCH-BACKEND",
                statement="Frontend fetches the backend API instead of serving static placeholder data.",
                evidence_required=("frontend_backend_integration_evidence", "frontend_source_inventory"),
                source_surface_refs=("frontend-ui", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-RUN-TEST-COMMANDS",
                statement="Package declares local run and test commands.",
                evidence_required=("run_manifest", "command_evidence"),
                source_surface_refs=("run-manifest", "tests"),
            ),
        ),
    )


def _criterion(
    *,
    acceptance_ref: str,
    statement: str,
    evidence_required: tuple[str, ...],
    source_surface_refs: tuple[str, ...],
) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        acceptance_ref=AcceptanceRef(value=acceptance_ref),
        statement=statement,
        evidence_required=tuple(EvidenceRequirement(value=value) for value in evidence_required),
        blocking=True,
        source_surface_refs=tuple(SourceSurfaceRef(value=value) for value in source_surface_refs),
        verification_strategy=VerificationStrategy(value="contract_fixture_and_later_runner_evidence"),
    )


def _package_contract(
    *,
    project_charter: ProjectCharter,
    methodology_profile: MethodologyProfile,
) -> PackageContract:
    methodology_registry = MethodologyProfileRegistry.from_profiles(methodology_profile)
    return create_package_contract(
        methodology_registry=methodology_registry,
        package_contract_id=ContractId(value="package-contract-tiny-fullstack"),
        project_charter_ref=project_charter.project_charter_id,
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface(
                surface_ref="backend-api",
                name="Backend API",
                paths=("backend/app.py",),
                acceptance_refs=(
                    "AC-TINY-API-BOOK-CREATE",
                    "AC-TINY-API-BOOK-LIST",
                    "AC-TINY-API-CHECKOUT-RETURN",
                ),
                required_tests=("test-backend", "test-integration"),
            ),
            _surface(
                surface_ref="frontend-ui",
                name="Frontend UI",
                paths=("frontend/index.html", "frontend/app.js"),
                acceptance_refs=("AC-TINY-UI-FETCH-BACKEND",),
                required_tests=("test-integration",),
            ),
            _surface(
                surface_ref="persistence",
                name="SQLite Persistence",
                paths=("backend/db.py",),
                acceptance_refs=("AC-TINY-PERSISTENCE-SQLITE",),
                required_tests=("test-backend", "test-integration"),
            ),
            _surface(
                surface_ref="tests",
                name="Project Tests",
                paths=("backend/tests/", "tests/integration/"),
                acceptance_refs=(
                    "AC-TINY-API-BOOK-CREATE",
                    "AC-TINY-API-BOOK-LIST",
                    "AC-TINY-API-CHECKOUT-RETURN",
                    "AC-TINY-PERSISTENCE-SQLITE",
                    "AC-TINY-UI-FETCH-BACKEND",
                    "AC-TINY-RUN-TEST-COMMANDS",
                ),
                required_tests=("test-backend", "test-integration"),
            ),
            _surface(
                surface_ref="docs",
                name="Project Documentation",
                paths=("README.md", "AGENTS.md"),
                acceptance_refs=("AC-TINY-RUN-TEST-COMMANDS",),
                required_tests=(),
            ),
            _surface(
                surface_ref="run-manifest",
                name="Run Manifest",
                paths=("run-manifest.json",),
                acceptance_refs=("AC-TINY-RUN-TEST-COMMANDS",),
                required_tests=("test-integration",),
            ),
        ),
        run_commands=(
            _command("run-backend", "Run backend API", ("python", "-m", "uvicorn", "backend.app:app")),
            _command("run-frontend", "Run frontend UI", ("python", "-m", "http.server", "5173", "--directory", "frontend")),
        ),
        test_commands=(
            _command("test-backend", "Run backend tests", ("pytest", "backend/tests")),
            _command("test-integration", "Run integration tests", ("pytest", "tests/integration")),
        ),
        integration_boundaries=(
            IntegrationBoundary(value="frontend-calls-backend-http-api"),
            IntegrationBoundary(value="backend-persists-book-state-in-sqlite"),
        ),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=methodology_profile.methodology_profile_id,
        docs_template_key=methodology_profile.docs_template_key,
        documentation_obligations=methodology_profile.documentation_obligations,
    )


def _surface(
    *,
    surface_ref: str,
    name: str,
    paths: tuple[str, ...],
    acceptance_refs: tuple[str, ...],
    required_tests: tuple[str, ...],
) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name=name,
        paths=paths,
        owned_by=OwnerSeatRef(value="worker-fullstack"),
        acceptance_refs=tuple(AcceptanceRef(value=value) for value in acceptance_refs),
        required_tests=tuple(RequiredTestRef(value=value) for value in required_tests),
    )


def _command(command_id: str, label: str, command: tuple[str, ...]) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=label,
        command=command,
        cwd=".",
    )
