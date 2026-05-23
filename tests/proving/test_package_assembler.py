from __future__ import annotations

import pytest
from pydantic import ValidationError

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
    PackageProjectType,
    create_package_contract,
)
from boardroom_os.contracts.source_surface import OwnerSeatRef, RequiredTestRef, SourceSurface
from boardroom_os.contracts.types import AcceptanceRef, ContractId, SourceSurfaceRef
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest

_VERIFY_ERRORS = (ValueError, ValidationError)


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.package-assembler"),
        project_charter_ref=ContractId(value="project.charter.package-assembler"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _surface(
    *,
    surface_ref: str,
    name: str,
    paths: tuple[str, ...],
    acceptance_refs: tuple[str, ...],
) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name=name,
        paths=paths,
        owned_by=OwnerSeatRef(value="worker-package"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest-package"),),
    )


def _command(command_id: str, label: str) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=label,
        command=("python", "-m", "pytest"),
        cwd=".",
    )


def _package_contract(
    *,
    docs_required: bool = True,
    project_type: PackageProjectType = PackageProjectType.SOFTWARE,
    source_surfaces: tuple[SourceSurface, ...] | None = None,
):
    profile = _profile()
    surfaces = source_surfaces or (
        _surface(
            surface_ref="backend-api",
            name="Backend API",
            paths=("backend/",),
            acceptance_refs=("AC-BACKEND",),
        ),
        _surface(
            surface_ref="frontend-ui",
            name="Frontend UI",
            paths=("frontend/",),
            acceptance_refs=("AC-FRONTEND",),
        ),
        _surface(
            surface_ref="package-tests",
            name="Package Tests",
            paths=("tests/",),
            acceptance_refs=("AC-TESTS",),
        ),
        _surface(
            surface_ref="run-manifest",
            name="Run Manifest",
            paths=("run-manifest.json",),
            acceptance_refs=("AC-RUN",),
        ),
        _surface(
            surface_ref="project-docs",
            name="Project Docs",
            paths=("docs/",),
            acceptance_refs=("AC-DOCS",),
        ),
    )
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.package-assembler"),
        project_charter_ref=ContractId(value="project.charter.package-assembler"),
        package_root="10-project",
        project_type=project_type,
        source_surfaces=surfaces,
        run_commands=(_command("run-package", "Run package"),),
        test_commands=(_command("test-package", "Test package"),),
        integration_boundaries=(IntegrationBoundary(value="local-http-api"),),
        docs_required=docs_required,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _manifest(package_contract=None):
    contract = package_contract or _package_contract()
    return build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-package-assembler"),
        workspace_root=WorkspacePath(value="workspace/workflow-package-assembler"),
        package_contract=contract,
    )


def _artifact(
    relative_path: str,
    kind,
    *,
    source_surface_refs: tuple[str, ...] = (),
    acceptance_refs: tuple[str, ...] = (),
):
    from boardroom_os.workspace.assembler import PackageArtifact, PackageArtifactPath

    return PackageArtifact(
        relative_path=PackageArtifactPath(value=relative_path),
        artifact_kind=kind,
        source_surface_refs=tuple(SourceSurfaceRef(value=ref) for ref in source_surface_refs),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
    )


def _tiny_artifacts():
    from boardroom_os.workspace.assembler import PackageArtifactKind

    return (
        _artifact("README.md", PackageArtifactKind.README),
        _artifact("AGENTS.md", PackageArtifactKind.AGENTS),
        _artifact(
            "package-contract.json",
            PackageArtifactKind.PACKAGE_CONTRACT,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        ),
        _artifact(
            "run-manifest.json",
            PackageArtifactKind.RUN_MANIFEST,
            source_surface_refs=("run-manifest",),
            acceptance_refs=("AC-RUN",),
        ),
        _artifact(
            "backend/app.py",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        ),
        _artifact(
            "frontend/App.tsx",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("frontend-ui",),
            acceptance_refs=("AC-FRONTEND",),
        ),
        _artifact(
            "tests/test_app.py",
            PackageArtifactKind.TEST,
            source_surface_refs=("package-tests",),
            acceptance_refs=("AC-TESTS",),
        ),
        _artifact(
            "docs/usage.md",
            PackageArtifactKind.DOC,
            source_surface_refs=("project-docs",),
            acceptance_refs=("AC-DOCS",),
        ),
    )


def _assemble(artifacts=None, package_contract=None):
    from boardroom_os.workspace.assembler import assemble_package

    contract = package_contract if package_contract is not None else _package_contract()
    return assemble_package(
        workspace_manifest=_manifest(contract),
        package_contract=contract,
        artifacts=artifacts if artifacts is not None else _tiny_artifacts(),
    )


def test_package_assembler_rejects_missing_package_contract_artifact() -> None:
    artifacts = tuple(
        artifact for artifact in _tiny_artifacts() if artifact.relative_path.value != "package-contract.json"
    )

    with pytest.raises(_VERIFY_ERRORS, match="package-contract.json"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_missing_run_manifest_artifact() -> None:
    artifacts = tuple(
        artifact for artifact in _tiny_artifacts() if artifact.relative_path.value != "run-manifest.json"
    )

    with pytest.raises(_VERIFY_ERRORS, match="run-manifest.json"):
        _assemble(artifacts=artifacts)


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/app.py",
        "../app.py",
        "20-evidence/source.json",
        "30-audit/process-audit.md",
        "00-boardroom/tickets/ticket.json",
        "10-project/src/app.py",
    ],
)
def test_package_artifact_path_rejects_paths_outside_package_root(bad_path: str) -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    with pytest.raises(_VERIFY_ERRORS, match="package artifact path|relative|parent|10-project|workspace"):
        _artifact(
            bad_path,
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        )


@pytest.mark.parametrize(
    "bad_path",
    ["src\\app.py", "src//app.py", "src/./app.py", "src/app.py/", "src/../app.py"],
)
def test_package_artifact_path_rejects_unsafe_path_shapes(bad_path: str) -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    with pytest.raises(_VERIFY_ERRORS, match="package artifact path|forward slashes|file|segment"):
        _artifact(
            bad_path,
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        )


@pytest.mark.parametrize(
    ("allowed_path", "artifact_kind", "surface_ref", "acceptance_ref"),
    [
        ("src/app.py", "source", "backend-api", "AC-BACKEND"),
        ("tests/test_app.py", "test", "package-tests", "AC-TESTS"),
        ("backend/app.py", "source", "backend-api", "AC-BACKEND"),
        ("frontend/App.tsx", "source", "frontend-ui", "AC-FRONTEND"),
    ],
)
def test_package_artifact_path_allows_generated_package_source_and_test_prefixes(
    allowed_path: str,
    artifact_kind: str,
    surface_ref: str,
    acceptance_ref: str,
) -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    artifact = _artifact(
        allowed_path,
        PackageArtifactKind(artifact_kind),
        source_surface_refs=(surface_ref,),
        acceptance_refs=(acceptance_ref,),
    )

    assert artifact.relative_path.value == allowed_path


@pytest.mark.parametrize(
    "framework_path",
    ["src/boardroom_os/runtime.py", "doc/spec.md", "scripts/build.py", "examples/demo.py"],
)
def test_package_artifact_path_rejects_framework_repo_prefixes(framework_path: str) -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    with pytest.raises(_VERIFY_ERRORS, match="framework|repository"):
        _artifact(
            framework_path,
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        )


def test_package_assembler_rejects_manifest_contract_mismatch() -> None:
    from boardroom_os.workspace.assembler import assemble_package

    contract = _package_contract()
    mismatched_contract = contract.model_copy(
        update={"package_contract_id": ContractId(value="package-contract.other")}
    )

    with pytest.raises(_VERIFY_ERRORS, match="package_contract_ref"):
        assemble_package(
            workspace_manifest=_manifest(contract),
            package_contract=mismatched_contract,
            artifacts=_tiny_artifacts(),
        )


def test_package_assembler_rejects_missing_readme() -> None:
    artifacts = tuple(artifact for artifact in _tiny_artifacts() if artifact.relative_path.value != "README.md")

    with pytest.raises(_VERIFY_ERRORS, match="README.md"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_missing_agents() -> None:
    artifacts = tuple(artifact for artifact in _tiny_artifacts() if artifact.relative_path.value != "AGENTS.md")

    with pytest.raises(_VERIFY_ERRORS, match="AGENTS.md"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_software_package_without_source_artifact() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    artifacts = tuple(
        artifact for artifact in _tiny_artifacts() if artifact.artifact_kind != PackageArtifactKind.SOURCE
    )

    with pytest.raises(_VERIFY_ERRORS, match="source artifacts"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_software_package_without_test_artifact() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    artifacts = tuple(
        artifact for artifact in _tiny_artifacts() if artifact.artifact_kind != PackageArtifactKind.TEST
    )

    with pytest.raises(_VERIFY_ERRORS, match="test artifacts"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_docs_required_without_doc_artifact() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    artifacts = tuple(
        artifact for artifact in _tiny_artifacts() if artifact.artifact_kind != PackageArtifactKind.DOC
    )

    with pytest.raises(_VERIFY_ERRORS, match="doc artifacts"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_unknown_source_surface_ref() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    artifacts = _tiny_artifacts() + (
        _artifact(
            "backend/extra.py",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("unknown-surface",),
            acceptance_refs=("AC-BACKEND",),
        ),
    )

    with pytest.raises(_VERIFY_ERRORS, match="unknown source surface"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_acceptance_ref_outside_source_surface() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    artifacts = _tiny_artifacts() + (
        _artifact(
            "backend/extra.py",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-FRONTEND",),
        ),
    )

    with pytest.raises(_VERIFY_ERRORS, match="acceptance refs outside source surface"):
        _assemble(artifacts=artifacts)


def test_package_assembler_rejects_incomplete_acceptance_ref_union_for_source_surface() -> None:
    contract = _package_contract(
        source_surfaces=(
            _surface(
                surface_ref="backend-api",
                name="Backend API",
                paths=("backend/",),
                acceptance_refs=("AC-BACKEND", "AC-BACKEND-SECURITY"),
            ),
            _surface(
                surface_ref="frontend-ui",
                name="Frontend UI",
                paths=("frontend/",),
                acceptance_refs=("AC-FRONTEND",),
            ),
            _surface(
                surface_ref="package-tests",
                name="Package Tests",
                paths=("tests/",),
                acceptance_refs=("AC-TESTS",),
            ),
            _surface(
                surface_ref="run-manifest",
                name="Run Manifest",
                paths=("run-manifest.json",),
                acceptance_refs=("AC-RUN",),
            ),
            _surface(
                surface_ref="project-docs",
                name="Project Docs",
                paths=("docs/",),
                acceptance_refs=("AC-DOCS",),
            ),
        )
    )

    with pytest.raises(_VERIFY_ERRORS, match="backend-api.*acceptance refs|acceptance refs.*backend-api"):
        _assemble(package_contract=contract)


def test_package_assembler_rejects_uncovered_source_surface_path() -> None:
    contract = _package_contract(
        source_surfaces=(
            _surface(
                surface_ref="backend-api",
                name="Backend API",
                paths=("backend/", "backend/migrations/"),
                acceptance_refs=("AC-BACKEND",),
            ),
            _surface(
                surface_ref="frontend-ui",
                name="Frontend UI",
                paths=("frontend/",),
                acceptance_refs=("AC-FRONTEND",),
            ),
            _surface(
                surface_ref="package-tests",
                name="Package Tests",
                paths=("tests/",),
                acceptance_refs=("AC-TESTS",),
            ),
            _surface(
                surface_ref="run-manifest",
                name="Run Manifest",
                paths=("run-manifest.json",),
                acceptance_refs=("AC-RUN",),
            ),
            _surface(
                surface_ref="project-docs",
                name="Project Docs",
                paths=("docs/",),
                acceptance_refs=("AC-DOCS",),
            ),
        )
    )

    with pytest.raises(_VERIFY_ERRORS, match="backend/migrations/"):
        _assemble(package_contract=contract)


def test_package_assembler_rejects_duplicate_artifact_paths() -> None:
    artifacts = _tiny_artifacts() + (_tiny_artifacts()[0],)

    with pytest.raises(_VERIFY_ERRORS, match="unique"):
        _assemble(artifacts=artifacts)


def test_package_artifact_rejects_wrong_kind_for_package_contract_file() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    with pytest.raises(_VERIFY_ERRORS, match="package-contract.json"):
        _artifact(
            "package-contract.json",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("backend-api",),
            acceptance_refs=("AC-BACKEND",),
        )


def test_package_artifact_rejects_wrong_kind_for_run_manifest_file() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    with pytest.raises(_VERIFY_ERRORS, match="run-manifest.json"):
        _artifact(
            "run-manifest.json",
            PackageArtifactKind.SOURCE,
            source_surface_refs=("run-manifest",),
            acceptance_refs=("AC-RUN",),
        )


def test_package_artifact_rejects_extra_fields() -> None:
    from boardroom_os.workspace.assembler import PackageArtifact, PackageArtifactKind, PackageArtifactPath

    with pytest.raises(ValidationError, match="Extra|extra"):
        PackageArtifact(
            relative_path=PackageArtifactPath(value="backend/app.py"),
            artifact_kind=PackageArtifactKind.SOURCE,
            source_surface_refs=(SourceSurfaceRef(value="backend-api"),),
            acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
            sha256="not-in-v2-060b",
        )


def test_package_assembler_builds_tiny_fullstack_package_assembly() -> None:
    from boardroom_os.workspace.assembler import PackageArtifactKind

    assembly = _assemble()

    assert (
        assembly.package_assembly_id.value
        == "package-assembly.workspace-manifest.workflow-package-assembler.package-contract.package-assembler"
    )
    assert assembly.workspace_manifest_ref.value == "workspace-manifest.workflow-package-assembler"
    assert assembly.package_contract_ref.value == "package-contract.package-assembler"
    assert assembly.package_root.value == "10-project"
    assert {artifact.relative_path.value for artifact in assembly.artifacts} == {
        "README.md",
        "AGENTS.md",
        "package-contract.json",
        "run-manifest.json",
        "backend/app.py",
        "frontend/App.tsx",
        "tests/test_app.py",
        "docs/usage.md",
    }
    assert {artifact.artifact_kind for artifact in assembly.artifacts} >= {
        PackageArtifactKind.SOURCE,
        PackageArtifactKind.TEST,
        PackageArtifactKind.DOC,
    }



def test_package_assembler_sorts_artifacts_for_stable_audit_output() -> None:
    artifacts = tuple(reversed(_tiny_artifacts()))

    assembly = _assemble(artifacts=artifacts)

    artifact_paths = tuple(artifact.relative_path.value for artifact in assembly.artifacts)
    assert artifact_paths == tuple(sorted(artifact_paths))



def test_package_assembler_repeated_builds_are_deterministic() -> None:
    first = _assemble()
    second = _assemble()

    assert first == second
    assert first.package_assembly_id == second.package_assembly_id
    assert tuple(artifact.relative_path.value for artifact in first.artifacts) == tuple(
        artifact.relative_path.value for artifact in second.artifacts
    )



def test_package_assembly_model_dump_is_audit_friendly() -> None:
    dump = _assemble().model_dump()

    assert dump["package_assembly_id"] == {
        "value": "package-assembly.workspace-manifest.workflow-package-assembler.package-contract.package-assembler"
    }
    assert dump["workspace_manifest_ref"] == {"value": "workspace-manifest.workflow-package-assembler"}
    assert dump["package_contract_ref"] == {"value": "package-contract.package-assembler"}
    assert dump["package_root"] == {"value": "10-project"}
    assert dump["artifacts"][0]["relative_path"] == {"value": "AGENTS.md"}



def test_workspace_package_exports_assembler_types() -> None:
    from boardroom_os.workspace import (
        PackageArtifact as ExportedPackageArtifact,
        PackageArtifactKind as ExportedPackageArtifactKind,
        PackageArtifactPath as ExportedPackageArtifactPath,
        PackageAssemblerError as ExportedPackageAssemblerError,
        PackageAssembly as ExportedPackageAssembly,
        PackageAssemblyRef as ExportedPackageAssemblyRef,
        assemble_package as exported_assemble_package,
    )
    from boardroom_os.workspace.assembler import (
        PackageArtifact,
        PackageArtifactKind,
        PackageArtifactPath,
        PackageAssemblerError,
        PackageAssembly,
        PackageAssemblyRef,
        assemble_package,
    )

    assert ExportedPackageArtifact is PackageArtifact
    assert ExportedPackageArtifactKind is PackageArtifactKind
    assert ExportedPackageArtifactPath is PackageArtifactPath
    assert ExportedPackageAssemblerError is PackageAssemblerError
    assert ExportedPackageAssembly is PackageAssembly
    assert ExportedPackageAssemblyRef is PackageAssemblyRef
    assert exported_assemble_package is assemble_package
