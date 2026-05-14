import pytest

import boardroom_os.contracts as contracts_pkg
from boardroom_os.contracts.methodology import (
    DocumentationDensity,
    DocumentationObligation,
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


_TEMPLATE_DENSITY_CASES = (
    (MethodologyTemplateKind.MINIMAL, DocumentationDensity.LIGHT),
    (MethodologyTemplateKind.AGILE, DocumentationDensity.STANDARD),
    (MethodologyTemplateKind.COMPLIANCE, DocumentationDensity.REGULATED),
    (MethodologyTemplateKind.HYBRID, DocumentationDensity.HEAVY),
)


def _surface() -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value="backend-api"),
        name="Backend API",
        paths=("backend/",),
        owned_by=OwnerSeatRef(value="worker-backend"),
        acceptance_refs=(AcceptanceRef(value="AC-METHOD-001"),),
        required_tests=(RequiredTestRef(value="pytest-backend"),),
    )


def _command(command_id: str, command: tuple[str, ...]) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id,
        command=command,
        cwd=".",
    )


def _package_contract_fields(profile: MethodologyProfile) -> dict[str, object]:
    return {
        "package_contract_id": ContractId(value=f"package-contract-{profile.template_kind.value}"),
        "project_charter_ref": profile.project_charter_ref,
        "package_root": f"packages/{profile.template_kind.value}",
        "project_type": PackageProjectType.SOFTWARE,
        "source_surfaces": (_surface(),),
        "run_commands": (_command("run-dev", ("python", "-m", "uvicorn", "app:app")),),
        "test_commands": (_command("test", ("pytest",)),),
        "integration_boundaries": (IntegrationBoundary(value="http-api"),),
        "docs_required": True,
        "closeout_required": True,
        "methodology_profile_ref": profile.methodology_profile_id,
        "docs_template_key": profile.docs_template_key,
        "documentation_obligations": profile.documentation_obligations,
    }


def test_methodology_module_provides_default_documentation_helpers() -> None:
    for template_kind in MethodologyTemplateKind:
        docs_template_key = docs_template_key_for(template_kind)
        documentation_obligations = default_documentation_obligations_for(template_kind)

        assert isinstance(docs_template_key, str)
        assert docs_template_key
        assert documentation_obligations
        assert all(
            isinstance(obligation, DocumentationObligation)
            for obligation in documentation_obligations
        )


@pytest.mark.parametrize(
    ("template_kind", "documentation_density"),
    _TEMPLATE_DENSITY_CASES,
    ids=[template_kind.value for template_kind, _ in _TEMPLATE_DENSITY_CASES],
)
def test_methodology_profile_binds_package_contract_and_exports_doc_fields(
    template_kind: MethodologyTemplateKind,
    documentation_density: DocumentationDensity,
) -> None:
    profile = MethodologyProfile(
        methodology_profile_id=ContractId(value=f"methodology-profile-{template_kind.value}"),
        project_charter_ref=ContractId(value="charter-001"),
        template_kind=template_kind,
        documentation_density=documentation_density,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )
    registry = MethodologyProfileRegistry.from_profiles(profile)

    contract = create_package_contract(
        methodology_registry=registry,
        **_package_contract_fields(profile),
    )
    dumped = contract.model_dump()

    assert profile.docs_template_key
    assert profile.documentation_obligations
    assert contract.methodology_profile_ref == profile.methodology_profile_id
    assert contract.docs_template_key == profile.docs_template_key
    assert contract.documentation_obligations == profile.documentation_obligations
    assert dumped["docs_template_key"] == profile.docs_template_key
    assert dumped["documentation_obligations"] == [
        obligation.model_dump() for obligation in profile.documentation_obligations
    ]


def test_contract_package_exports_methodology_types_factory_and_helpers() -> None:
    assert contracts_pkg.DocumentationDensity is DocumentationDensity
    assert contracts_pkg.DocumentationObligation is DocumentationObligation
    assert contracts_pkg.MethodologyProfile is MethodologyProfile
    assert contracts_pkg.MethodologyProfileRegistry is MethodologyProfileRegistry
    assert contracts_pkg.MethodologyTemplateKind is MethodologyTemplateKind
    assert contracts_pkg.create_package_contract is create_package_contract
    assert contracts_pkg.docs_template_key_for is docs_template_key_for
    assert (
        contracts_pkg.default_documentation_obligations_for
        is default_documentation_obligations_for
    )


def test_documentation_package_without_required_docs_allows_direct_constructor() -> None:
    contract = PackageContract(
        package_contract_id=ContractId(value="package-contract-docs-001"),
        project_charter_ref=ContractId(value="charter-001"),
        package_root="packages/docs-only",
        project_type=PackageProjectType.DOCUMENTATION,
        source_surfaces=(
            SourceSurface(
                source_surface_ref=SourceSurfaceRef(value="docs"),
                name="Documentation",
                paths=("README.md", "docs/"),
                owned_by=OwnerSeatRef(value="worker-docs"),
                acceptance_refs=(AcceptanceRef(value="AC-DOCS-001"),),
                required_tests=(),
            ),
        ),
        run_commands=(),
        test_commands=(),
        integration_boundaries=(),
        docs_required=False,
        closeout_required=True,
        documentation_obligations=(),
    )

    assert contract.docs_required is False
    assert contract.methodology_profile_ref is None
    assert contract.docs_template_key is None
    assert contract.documentation_obligations == ()
