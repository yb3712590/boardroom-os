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
    "AC-TINY-API-BOOK-DELETE": ("AC-V2-CONTRACT-001", "AC-V2-PACKAGE-002"),
    "AC-TINY-PERSISTENCE-SQLITE": ("AC-V2-CONTRACT-001", "AC-V2-EVIDENCE-003"),
    "AC-TINY-BACKEND-STARTUP": (
        "AC-V2-CONTRACT-002",
        "AC-V2-EVIDENCE-004",
        "AC-V2-PACKAGE-002",
    ),
    "AC-TINY-BACKEND-HTTP-CRUD": (
        "AC-V2-CONTRACT-001",
        "AC-V2-EVIDENCE-004",
        "AC-V2-PACKAGE-002",
    ),
    "AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP": (
        "AC-V2-CONTRACT-001",
        "AC-V2-EVIDENCE-004",
    ),
    "AC-TINY-FRONTEND-STARTUP": (
        "AC-V2-CONTRACT-002",
        "AC-V2-EVIDENCE-004",
        "AC-V2-PACKAGE-002",
    ),
    "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION": (
        "AC-V2-CONTRACT-001",
        "AC-V2-EVIDENCE-004",
        "AC-V2-PACKAGE-001",
    ),
    "AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED": (
        "AC-V2-EVIDENCE-001",
        "AC-V2-PACKAGE-002",
        "AC-V2-PACKAGE-003",
    ),
}

_ALLOWED_AC_V2_REFS = {
    "AC-V2-CONTRACT-001",
    "AC-V2-CONTRACT-002",
    "AC-V2-CONTRACT-003",
    "AC-V2-EVIDENCE-001",
    "AC-V2-EVIDENCE-003",
    "AC-V2-EVIDENCE-004",
    "AC-V2-EXECUTION-003",
    "AC-V2-PACKAGE-001",
    "AC-V2-PACKAGE-002",
    "AC-V2-PACKAGE-003",
}
_FALLBACK_FORBIDDEN_ACCEPTANCE_REF = "AC-TINY-EVIDENCE-NO-FALLBACK"
_STANDARD_LIBRARY_PROVIDER_POLICY = (
    "Use only Python standard library modules. Do not use Flask, FastAPI, "
    "requests, npm, uvicorn, or other third-party packages. Implement "
    "backend/app.py as a standard-library HTTP service with http.server, "
    "BaseHTTPRequestHandler, and python -m backend.app. Require /health, "
    "/books, checkout, return, DELETE endpoints, SQLite persistence via "
    "HTTP, and final live integration evidence; fakeFetch-only cannot "
    "satisfy final integration evidence."
)


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
    validate_tiny_fullstack_contract_recovery(
        acceptance_contract=acceptance_contract,
        package_contract=package_contract,
        provider_system_instructions=_STANDARD_LIBRARY_PROVIDER_POLICY,
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


def validate_tiny_fullstack_contract_recovery(
    *,
    acceptance_contract: AcceptanceContract,
    package_contract: PackageContract,
    provider_system_instructions: str,
) -> None:
    _validate_tiny_standard_library_backend_route(
        package_contract=package_contract,
        provider_system_instructions=provider_system_instructions,
    )
    _validate_live_http_acceptance(acceptance_contract)
    _validate_final_command_evidence_acceptance(acceptance_contract)
    _validate_tiny_integration_boundaries(package_contract)


def _validate_tiny_standard_library_backend_route(
    *,
    package_contract: PackageContract,
    provider_system_instructions: str,
) -> None:
    backend_command = _package_command_by_id(package_contract, "run-backend")
    command_text = " ".join(backend_command.command).lower()
    third_party_markers = ("uvicorn", "flask", "fastapi", "starlette")
    if any(marker in command_text for marker in third_party_markers):
        raise ValueError(
            "tiny contract standard-library HTTP route cannot use uvicorn or third-party servers"
        )
    if backend_command.command != ("python", "-m", "backend.app"):
        raise ValueError(
            "tiny contract standard-library HTTP route requires run-backend to execute python -m backend.app"
        )
    _validate_tiny_provider_prompt_http_route(provider_system_instructions)


def _validate_tiny_provider_prompt_http_route(provider_system_instructions: str) -> None:
    if not provider_system_instructions.strip():
        raise ValueError("tiny provider prompt is required for standard-library HTTP route")
    required_markers = (
        "Python standard library modules",
        "http.server",
        "BaseHTTPRequestHandler",
        "python -m backend.app",
        "/health",
        "/books",
        "SQLite persistence via HTTP",
        "fakeFetch-only",
    )
    missing_markers = tuple(
        marker
        for marker in required_markers
        if marker not in provider_system_instructions
    )
    if missing_markers:
        raise ValueError(
            "tiny provider prompt must require "
            f"{', '.join(missing_markers)} for standard-library HTTP route"
        )


def _validate_live_http_acceptance(acceptance_contract: AcceptanceContract) -> None:
    criterion = _blocking_criterion_by_ref(
        acceptance_contract,
        "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
    )
    evidence_required = {evidence.value for evidence in criterion.evidence_required}
    if "live_frontend_backend_integration_evidence" not in evidence_required:
        raise ValueError("live HTTP integration evidence is required for frontend/backend acceptance")
    statement = criterion.statement.lower()
    required_markers = ("live", "http", "backend")
    if any(marker not in statement for marker in required_markers):
        raise ValueError("live HTTP integration evidence must be explicit in acceptance statement")


def _validate_final_command_evidence_acceptance(acceptance_contract: AcceptanceContract) -> None:
    criterion = _blocking_criterion_by_ref(
        acceptance_contract,
        "AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",
    )
    evidence_required = {evidence.value for evidence in criterion.evidence_required}
    required = {
        "run_manifest",
        "backend_service_run",
        "frontend_service_run",
        "test_command_evidence",
        "final_command_evidence",
    }
    if not required.issubset(evidence_required):
        raise ValueError("final command evidence is required for all declared run/test commands")


def _validate_tiny_integration_boundaries(package_contract: PackageContract) -> None:
    boundaries = {boundary.value for boundary in package_contract.integration_boundaries}
    required_boundaries = {
        "frontend-calls-live-backend-http-api",
        "backend-persists-book-state-in-sqlite-via-http",
        "backend-standard-library-http-service",
        "frontend-static-service",
    }
    if not required_boundaries.issubset(boundaries):
        raise ValueError("tiny package integration boundaries must require live HTTP services")


def _blocking_criterion_by_ref(
    acceptance_contract: AcceptanceContract,
    acceptance_ref: str,
) -> AcceptanceCriterion:
    for criterion in acceptance_contract.blocking_criteria():
        if criterion.acceptance_ref == AcceptanceRef(value=acceptance_ref):
            return criterion
    raise ValueError(f"missing tiny acceptance criterion: {acceptance_ref}")


def _package_command_by_id(package_contract: PackageContract, command_id: str) -> PackageCommand:
    for command in (*package_contract.run_commands, *package_contract.test_commands):
        if command.command_id == ContractId(value=command_id):
            return command
    raise ValueError(f"missing package command: {command_id}")


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
                statement="Backend HTTP API can create books through POST /books.",
                evidence_required=("backend_http_api_evidence", "backend_source_inventory"),
                source_surface_refs=("backend-api", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-API-BOOK-LIST",
                statement="Backend HTTP API can list books through GET /books.",
                evidence_required=("backend_http_api_evidence", "backend_source_inventory"),
                source_surface_refs=("backend-api", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-API-CHECKOUT-RETURN",
                statement="Backend HTTP API supports checkout and return state transitions.",
                evidence_required=("backend_http_api_evidence", "backend_source_inventory"),
                source_surface_refs=("backend-api", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-API-BOOK-DELETE",
                statement="Backend HTTP API can delete books through DELETE /books/{id}.",
                evidence_required=("backend_http_api_evidence", "backend_source_inventory"),
                source_surface_refs=("backend-api", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-PERSISTENCE-SQLITE",
                statement="SQLite persistence records book state.",
                evidence_required=("sqlite_persistence_evidence", "backend_source_inventory"),
                source_surface_refs=("persistence", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-BACKEND-STARTUP",
                statement="Backend run command starts a live standard-library HTTP service and passes /health readiness.",
                evidence_required=("backend_service_run", "backend_source_inventory"),
                source_surface_refs=("backend-api", "run-manifest", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-BACKEND-HTTP-CRUD",
                statement="Live backend HTTP service supports create, list, checkout, return, and delete CRUD flow.",
                evidence_required=("backend_http_crud_evidence", "backend_source_inventory"),
                source_surface_refs=("backend-api", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP",
                statement="SQLite persistence is proven through the live HTTP workflow.",
                evidence_required=("sqlite_persistence_http_evidence", "backend_source_inventory"),
                source_surface_refs=("persistence", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-FRONTEND-STARTUP",
                statement="Frontend run command starts a live static frontend service.",
                evidence_required=("frontend_service_run", "frontend_source_inventory"),
                source_surface_refs=("frontend-ui", "run-manifest", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
                statement="Frontend code performs live HTTP integration with the running backend service.",
                evidence_required=("live_frontend_backend_integration_evidence", "frontend_source_inventory"),
                source_surface_refs=("frontend-ui", "tests"),
            ),
            _criterion(
                acceptance_ref="AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",
                statement="Every declared run and test command has final command evidence.",
                evidence_required=(
                    "run_manifest",
                    "backend_service_run",
                    "frontend_service_run",
                    "test_command_evidence",
                    "final_command_evidence",
                ),
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
                    "AC-TINY-API-BOOK-DELETE",
                    "AC-TINY-BACKEND-STARTUP",
                    "AC-TINY-BACKEND-HTTP-CRUD",
                ),
                required_tests=("test-backend", "test-integration"),
            ),
            _surface(
                surface_ref="frontend-ui",
                name="Frontend UI",
                paths=("frontend/index.html", "frontend/app.js"),
                acceptance_refs=(
                    "AC-TINY-FRONTEND-STARTUP",
                    "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
                ),
                required_tests=("test-integration",),
            ),
            _surface(
                surface_ref="persistence",
                name="SQLite Persistence",
                paths=("backend/db.py",),
                acceptance_refs=("AC-TINY-PERSISTENCE-SQLITE", "AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP"),
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
                    "AC-TINY-API-BOOK-DELETE",
                    "AC-TINY-PERSISTENCE-SQLITE",
                    "AC-TINY-BACKEND-STARTUP",
                    "AC-TINY-BACKEND-HTTP-CRUD",
                    "AC-TINY-SQLITE-PERSISTENCE-VIA-HTTP",
                    "AC-TINY-FRONTEND-STARTUP",
                    "AC-TINY-FRONTEND-LIVE-BACKEND-INTEGRATION",
                    "AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",
                ),
                required_tests=("test-backend", "test-integration"),
            ),
            _surface(
                surface_ref="docs",
                name="Project Documentation",
                paths=("README.md", "AGENTS.md", "docs/usage.md"),
                acceptance_refs=("AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",),
                required_tests=("test-integration",),
            ),
            _surface(
                surface_ref="run-manifest",
                name="Run Manifest",
                paths=("run-manifest.json",),
                acceptance_refs=(
                    "AC-TINY-BACKEND-STARTUP",
                    "AC-TINY-FRONTEND-STARTUP",
                    "AC-TINY-ALL-RUN-AND-TEST-COMMANDS-VERIFIED",
                ),
                required_tests=("test-integration",),
            ),
        ),
        run_commands=(
            _command("run-backend", "Run backend API", ("python", "-m", "backend.app")),
            _command("run-frontend", "Run frontend UI", ("python", "-m", "http.server", "5173", "--directory", "frontend")),
        ),
        test_commands=(
            _command(
                "test-backend",
                "Run backend tests",
                (
                    "python",
                    "-X",
                    "utf8",
                    "-m",
                    "pytest",
                    "backend/tests",
                    "--basetemp=.pytest-tmp-backend",
                ),
            ),
            _command(
                "test-integration",
                "Run integration tests",
                (
                    "python",
                    "-X",
                    "utf8",
                    "-m",
                    "pytest",
                    "tests/integration",
                    "--basetemp=.pytest-tmp-integration",
                ),
            ),
        ),
        integration_boundaries=(
            IntegrationBoundary(value="backend-standard-library-http-service"),
            IntegrationBoundary(value="frontend-static-service"),
            IntegrationBoundary(value="frontend-calls-live-backend-http-api"),
            IntegrationBoundary(value="backend-persists-book-state-in-sqlite-via-http"),
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
