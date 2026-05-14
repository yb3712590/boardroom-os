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
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, SourceSurfaceRef


def _surface(
    *,
    surface_ref: str,
    name: str,
    paths: tuple[str, ...],
    acceptance_refs: tuple[str, ...],
    required_tests: tuple[str, ...] = (),
) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name=name,
        paths=paths,
        owned_by=OwnerSeatRef(value="worker-fullstack"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=tuple(RequiredTestRef(value=ref) for ref in required_tests),
    )


def _command(command_id: str, label: str, command: tuple[str, ...]) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=label,
        command=command,
        cwd=".",
    )


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile-hybrid"),
        project_charter_ref=ContractId(value="charter-001"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _registry(profile: MethodologyProfile | None = None) -> MethodologyProfileRegistry:
    resolved_profile = profile or _profile()
    return MethodologyProfileRegistry.from_profiles(resolved_profile)


def test_tiny_fullstack_package_contract_declares_required_surfaces_and_commands() -> None:
    profile = _profile()
    contract = create_package_contract(
        methodology_registry=_registry(profile),
        package_contract_id=ContractId(value="package-contract-001"),
        project_charter_ref=ContractId(value="charter-001"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface(
                surface_ref="backend-api",
                name="Backend API",
                paths=("backend/",),
                acceptance_refs=("AC-BOOK-API-001",),
                required_tests=("pytest-backend",),
            ),
            _surface(
                surface_ref="frontend-ui",
                name="Frontend UI",
                paths=("frontend/",),
                acceptance_refs=("AC-BOOK-UI-001",),
                required_tests=("vitest-frontend",),
            ),
            _surface(
                surface_ref="tests",
                name="Project Tests",
                paths=("tests/",),
                acceptance_refs=("AC-BOOK-RUN-001", "AC-BOOK-TEST-001"),
                required_tests=("pytest", "vitest"),
            ),
            _surface(
                surface_ref="docs",
                name="Project Documentation",
                paths=("README.md", "docs/"),
                acceptance_refs=("AC-BOOK-DOCS-001",),
            ),
            _surface(
                surface_ref="run-manifest",
                name="Run Manifest",
                paths=("run-manifest.json",),
                acceptance_refs=("AC-BOOK-RUN-001",),
            ),
        ),
        run_commands=(
            _command("run-backend", "Run backend API", ("python", "-m", "uvicorn", "backend.app:app")),
            _command("run-frontend", "Run frontend UI", ("npm", "run", "dev")),
        ),
        test_commands=(
            _command("test-backend", "Run backend tests", ("pytest", "tests/backend")),
            _command("test-frontend", "Run frontend tests", ("npm", "test")),
        ),
        integration_boundaries=(
            IntegrationBoundary(value="frontend-calls-backend-http-api"),
            IntegrationBoundary(value="backend-persists-book-state"),
        ),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )

    assert contract.package_root == "10-project"
    assert contract.project_type == PackageProjectType.SOFTWARE
    assert [surface.source_surface_ref.value for surface in contract.source_surfaces] == [
        "backend-api",
        "frontend-ui",
        "tests",
        "docs",
        "run-manifest",
    ]
    assert [command.command_id.value for command in contract.run_commands] == [
        "run-backend",
        "run-frontend",
    ]
    assert [command.command_id.value for command in contract.test_commands] == [
        "test-backend",
        "test-frontend",
    ]
    assert contract.model_dump()["source_surfaces"][0]["acceptance_refs"] == [
        {"value": "AC-BOOK-API-001"}
    ]


def test_documentation_package_contract_allows_empty_run_and_test_commands() -> None:
    contract = PackageContract(
        package_contract_id=ContractId(value="package-contract-docs-001"),
        project_charter_ref=ContractId(value="charter-001"),
        package_root="10-project",
        project_type=PackageProjectType.DOCUMENTATION,
        source_surfaces=(
            _surface(
                surface_ref="docs",
                name="Project Documentation",
                paths=("README.md", "docs/"),
                acceptance_refs=("AC-DOCS-001",),
            ),
        ),
        run_commands=(),
        test_commands=(),
        integration_boundaries=(),
        docs_required=False,
        closeout_required=True,
    )

    assert contract.run_commands == ()
    assert contract.test_commands == ()


def test_contract_package_exports_package_contract_types() -> None:
    from boardroom_os.contracts import (
        IntegrationBoundary,
        OwnerSeatRef,
        PackageCommand,
        PackageContract,
        PackageProjectType,
        RequiredTestRef,
        SourceSurface,
    )

    assert IntegrationBoundary.__name__ == "IntegrationBoundary"
    assert OwnerSeatRef.__name__ == "OwnerSeatRef"
    assert PackageCommand.__name__ == "PackageCommand"
    assert PackageContract.__name__ == "PackageContract"
    assert PackageProjectType.SOFTWARE == "software"
    assert RequiredTestRef.__name__ == "RequiredTestRef"
    assert SourceSurface.__name__ == "SourceSurface"
