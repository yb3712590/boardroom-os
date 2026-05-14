import pytest
from pydantic import ValidationError

from boardroom_os.contracts.methodology import (
    DocumentationDensity,
    DocumentationObligation,
    MethodologyProfile,
    MethodologyProfileRegistry,
    MethodologyTemplateKind,
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


def _surface(surface_ref: str = "backend-api") -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
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


def _documentation_obligation(
    obligation_id: str = "doc-architecture",
    artifact_name: str = "Architecture Notes",
    *,
    required: bool = True,
) -> DocumentationObligation:
    return DocumentationObligation(
        obligation_id=ContractId(value=obligation_id),
        artifact_name=artifact_name,
        required=required,
        audience="delivery-reviewers",
        purpose="prove the package satisfies methodology-specific documentation requirements",
    )


def _documentation_obligations(
    obligation_id: str = "doc-architecture",
    artifact_name: str = "Architecture Notes",
    *,
    required: bool = True,
) -> tuple[DocumentationObligation, ...]:
    return (
        _documentation_obligation(
            obligation_id=obligation_id,
            artifact_name=artifact_name,
            required=required,
        ),
    )


def _profile(
    *,
    methodology_profile_id: str = "methodology-profile-compliance-regulated",
    template_kind: MethodologyTemplateKind = MethodologyTemplateKind.COMPLIANCE,
    documentation_density: DocumentationDensity = DocumentationDensity.REGULATED,
    docs_template_key: str | None = None,
    documentation_obligations: tuple[DocumentationObligation, ...] | None = None,
) -> MethodologyProfile:
    return MethodologyProfile(
        methodology_profile_id=ContractId(value=methodology_profile_id),
        project_charter_ref=ContractId(value="charter-001"),
        template_kind=template_kind,
        documentation_density=documentation_density,
        docs_template_key=(
            docs_template_key
            if docs_template_key is not None
            else f"{methodology_profile_id}-template"
        ),
        documentation_obligations=(
            documentation_obligations
            if documentation_obligations is not None
            else _documentation_obligations()
        ),
    )


def _registry(*profiles: MethodologyProfile) -> MethodologyProfileRegistry:
    if not profiles:
        profiles = (_profile(),)
    return MethodologyProfileRegistry.from_profiles(*profiles)


def _create_package_contract(
    *,
    profile: MethodologyProfile | None = None,
    registry: MethodologyProfileRegistry | None = None,
    docs_required: bool = True,
    include_methodology_profile_ref: bool = True,
    include_docs_template_key: bool = True,
    docs_template_key: str | None = None,
    project_charter_ref: ContractId | None = None,
    documentation_obligations: tuple[DocumentationObligation, ...] | None = None,
):
    resolved_profile = profile or _profile()
    resolved_registry = registry or _registry(resolved_profile)

    contract_fields: dict[str, object] = {
        "package_contract_id": ContractId(value="package-contract-001"),
        "project_charter_ref": (
            project_charter_ref
            if project_charter_ref is not None
            else ContractId(value="charter-001")
        ),
        "package_root": "10-project",
        "project_type": PackageProjectType.SOFTWARE,
        "source_surfaces": (_surface(),),
        "run_commands": (_command("run-dev", ("python", "-m", "uvicorn", "app:app")),),
        "test_commands": (_command("test", ("pytest",)),),
        "integration_boundaries": (IntegrationBoundary(value="http-api"),),
        "docs_required": docs_required,
        "closeout_required": True,
        "documentation_obligations": (
            documentation_obligations
            if documentation_obligations is not None
            else resolved_profile.documentation_obligations
        ),
    }
    if include_methodology_profile_ref:
        contract_fields["methodology_profile_ref"] = resolved_profile.methodology_profile_id
    if include_docs_template_key:
        contract_fields["docs_template_key"] = (
            docs_template_key
            if docs_template_key is not None
            else resolved_profile.docs_template_key
        )

    return create_package_contract(
        methodology_registry=resolved_registry,
        **contract_fields,
    )


def test_methodology_profile_requires_template_kind() -> None:
    with pytest.raises(ValidationError, match="template_kind"):
        MethodologyProfile(
            methodology_profile_id=ContractId(value="methodology-profile-001"),
            project_charter_ref=ContractId(value="charter-001"),
            documentation_density=DocumentationDensity.STANDARD,
            docs_template_key="hybrid-standard-template",
            documentation_obligations=_documentation_obligations(),
        )


def test_methodology_profile_requires_documentation_density() -> None:
    with pytest.raises(ValidationError, match="documentation_density"):
        MethodologyProfile(
            methodology_profile_id=ContractId(value="methodology-profile-001"),
            project_charter_ref=ContractId(value="charter-001"),
            template_kind=MethodologyTemplateKind.HYBRID,
            docs_template_key="hybrid-standard-template",
            documentation_obligations=_documentation_obligations(),
        )


def test_methodology_profile_rejects_unknown_template_kind() -> None:
    with pytest.raises(ValidationError):
        MethodologyProfile(
            methodology_profile_id=ContractId(value="methodology-profile-001"),
            project_charter_ref=ContractId(value="charter-001"),
            template_kind="waterfall",
            documentation_density=DocumentationDensity.STANDARD,
            docs_template_key="legacy-template-key",
            documentation_obligations=_documentation_obligations(),
        )


@pytest.mark.parametrize(
    ("template_kind", "documentation_density", "docs_template_key"),
    (
        (
            MethodologyTemplateKind.MINIMAL,
            DocumentationDensity.REGULATED,
            "minimal-regulated-template-key",
        ),
        (
            MethodologyTemplateKind.COMPLIANCE,
            DocumentationDensity.LIGHT,
            "compliance-light-template-key",
        ),
    ),
)
def test_methodology_profile_rejects_invalid_template_and_density_combinations(
    template_kind: MethodologyTemplateKind,
    documentation_density: DocumentationDensity,
    docs_template_key: str,
) -> None:
    with pytest.raises(ValidationError):
        MethodologyProfile(
            methodology_profile_id=ContractId(value="methodology-profile-invalid-combination"),
            project_charter_ref=ContractId(value="charter-001"),
            template_kind=template_kind,
            documentation_density=documentation_density,
            docs_template_key=docs_template_key,
            documentation_obligations=_documentation_obligations(),
        )


def test_methodology_profile_registry_rejects_duplicate_profile_ids() -> None:
    profile = _profile()
    duplicate_profile = _profile(
        docs_template_key="duplicate-template-key",
        documentation_obligations=_documentation_obligations(
            obligation_id="doc-duplicate",
            artifact_name="Duplicate Notes",
        ),
    )

    with pytest.raises(ValidationError, match="methodology_profile_id"):
        MethodologyProfileRegistry.from_profiles(profile, duplicate_profile)


def test_methodology_profile_registry_rejects_duplicate_normalized_profile_ids() -> None:
    constructed_profile = MethodologyProfile.model_construct(
        methodology_profile_id=ContractId.model_construct(value=" methodology-profile-001 "),
        project_charter_ref=ContractId(value="charter-001"),
        template_kind=MethodologyTemplateKind.COMPLIANCE,
        documentation_density=DocumentationDensity.REGULATED,
        docs_template_key="constructed-template-key",
        documentation_obligations=_documentation_obligations(
            obligation_id="doc-constructed",
            artifact_name="Constructed Notes",
        ),
    )
    profile = _profile(methodology_profile_id="methodology-profile-001")

    with pytest.raises(ValidationError, match="methodology_profile_id"):
        MethodologyProfileRegistry.from_profiles(constructed_profile, profile)


def test_methodology_profile_registry_rejects_non_iterable_profiles_with_validation_error() -> None:
    with pytest.raises(ValidationError, match="profiles must be iterable"):
        MethodologyProfileRegistry.model_validate({"profiles": 1})


def test_methodology_profile_registry_rejects_empty_iterator_profiles() -> None:
    with pytest.raises(ValidationError, match="profiles must not be empty"):
        MethodologyProfileRegistry.model_validate({"profiles": iter(())})


def test_methodology_profile_registry_rejects_duplicate_normalized_nested_dict_ids() -> None:
    constructed_profile = {
        "methodology_profile_id": ContractId.model_construct(
            value=" methodology-profile-001 ",
        ),
        "project_charter_ref": ContractId(value="charter-001"),
        "template_kind": MethodologyTemplateKind.COMPLIANCE,
        "documentation_density": DocumentationDensity.REGULATED,
        "docs_template_key": "nested-dict-template-key",
        "documentation_obligations": _documentation_obligations(
            obligation_id="doc-nested-dict",
            artifact_name="Nested Dict Notes",
        ),
    }
    profile = _profile(methodology_profile_id="methodology-profile-001")

    with pytest.raises(ValidationError, match="methodology_profile_id"):
        MethodologyProfileRegistry.model_validate(
            {"profiles": (constructed_profile, profile)},
        )


def test_methodology_profile_registry_revalidates_constructed_profiles() -> None:
    invalid_profile = MethodologyProfile.model_construct(
        methodology_profile_id=ContractId(value="methodology-profile-constructed-invalid"),
        project_charter_ref=ContractId(value="charter-001"),
        template_kind="waterfall",
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key="",
        documentation_obligations=(),
    )

    with pytest.raises(ValidationError):
        MethodologyProfileRegistry.from_profiles(invalid_profile)


def test_package_contract_requires_methodology_profile_ref_when_docs_required() -> None:
    with pytest.raises(ValidationError, match="methodology_profile_ref"):
        _create_package_contract(include_methodology_profile_ref=False)


def test_package_contract_direct_constructor_rejects_docs_required_without_registry_context() -> None:
    profile = _profile()

    with pytest.raises(ValidationError, match="methodology registry"):
        PackageContract(
            package_contract_id=ContractId(value="package-contract-direct-001"),
            project_charter_ref=profile.project_charter_ref,
            package_root="10-project",
            project_type=PackageProjectType.SOFTWARE,
            source_surfaces=(_surface(),),
            run_commands=(_command("run-dev", ("python", "-m", "uvicorn", "app:app")),),
            test_commands=(_command("test", ("pytest",)),),
            integration_boundaries=(IntegrationBoundary(value="http-api"),),
            docs_required=True,
            closeout_required=True,
            methodology_profile_ref=profile.methodology_profile_id,
            docs_template_key=profile.docs_template_key,
            documentation_obligations=profile.documentation_obligations,
        )


def test_package_contract_requires_docs_template_key_when_docs_required() -> None:
    with pytest.raises(ValidationError, match="docs_template_key"):
        _create_package_contract(include_docs_template_key=False)


def test_package_contract_requires_documentation_obligations_when_docs_required() -> None:
    with pytest.raises(ValidationError, match="documentation_obligations"):
        _create_package_contract(documentation_obligations=())


def test_package_contract_rejects_required_documentation_when_docs_not_required() -> None:
    profile = _profile(
        methodology_profile_id="methodology-profile-optional-docs-mismatch",
        template_kind=MethodologyTemplateKind.HYBRID,
        documentation_density=DocumentationDensity.STANDARD,
        documentation_obligations=_documentation_obligations(
            obligation_id="doc-closeout",
            artifact_name="Closeout Summary",
        ),
    )

    with pytest.raises(ValidationError):
        _create_package_contract(
            profile=profile,
            registry=_registry(profile),
            docs_required=False,
        )


def test_package_contract_rejects_package_project_charter_mismatched_with_profile() -> None:
    profile = _profile()

    with pytest.raises(ValidationError, match="project_charter_ref"):
        _create_package_contract(
            profile=profile,
            registry=_registry(profile),
            project_charter_ref=ContractId(value="charter-other"),
        )


def test_package_contract_rejects_docs_template_key_mismatched_with_profile() -> None:
    profile = _profile()

    with pytest.raises(ValidationError, match="docs_template_key"):
        _create_package_contract(
            profile=profile,
            registry=_registry(profile),
            docs_template_key="other-template-key",
        )


def test_package_contract_rejects_documentation_obligations_mismatched_with_profile() -> None:
    profile = _profile(
        methodology_profile_id="methodology-profile-hybrid-standard",
        template_kind=MethodologyTemplateKind.HYBRID,
        documentation_density=DocumentationDensity.STANDARD,
        documentation_obligations=_documentation_obligations(
            obligation_id="doc-hybrid-architecture",
            artifact_name="Hybrid Architecture Notes",
        ),
    )
    alternate_profile = _profile(
        methodology_profile_id="methodology-profile-compliance-heavy",
        template_kind=MethodologyTemplateKind.COMPLIANCE,
        documentation_density=DocumentationDensity.HEAVY,
        documentation_obligations=_documentation_obligations(
            obligation_id="doc-compliance-evidence",
            artifact_name="Compliance Evidence Pack",
        ),
    )

    with pytest.raises(ValidationError, match="documentation_obligations"):
        _create_package_contract(
            profile=profile,
            registry=_registry(profile, alternate_profile),
            documentation_obligations=alternate_profile.documentation_obligations,
        )
