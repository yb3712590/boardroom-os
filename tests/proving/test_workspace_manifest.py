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

_VERIFY_ERRORS = (ValueError, ValidationError)


def _surface(
    *,
    surface_ref: str = "backend-api",
    paths: tuple[str, ...] = ("backend/",),
    acceptance_refs: tuple[str, ...] = ("AC-BACKEND",),
) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name="Backend API",
        paths=paths,
        owned_by=OwnerSeatRef(value="worker-backend"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest-backend"),),
    )


def _command(command_id: str = "test-backend") -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label="Run backend tests",
        command=("pytest", "tests/backend"),
        cwd=".",
    )


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.workspace"),
        project_charter_ref=ContractId(value="project.charter.workspace"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _package_contract(*, package_root: str = "10-project"):
    profile = _profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.workspace"),
        project_charter_ref=ContractId(value="project.charter.workspace"),
        package_root=package_root,
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface(),
            SourceSurface(
                source_surface_ref=SourceSurfaceRef(value="run-manifest"),
                name="Run Manifest",
                paths=("run-manifest.json",),
                owned_by=OwnerSeatRef(value="worker-backend"),
                acceptance_refs=(AcceptanceRef(value="AC-RUN"),),
                required_tests=(RequiredTestRef(value="pytest-backend"),),
            ),
        ),
        run_commands=(_command("run-backend"),),
        test_commands=(_command("test-backend"),),
        integration_boundaries=(IntegrationBoundary(value="backend-http-api"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _manifest_sections():
    from boardroom_os.workspace.manifest import WorkspaceSection, WorkspaceSectionPath, WorkspacePath

    return (
        WorkspaceSectionPath(section=WorkspaceSection.BOARDROOM, relative_path=WorkspacePath(value="00-boardroom")),
        WorkspaceSectionPath(section=WorkspaceSection.PROJECT, relative_path=WorkspacePath(value="10-project")),
        WorkspaceSectionPath(section=WorkspaceSection.EVIDENCE, relative_path=WorkspacePath(value="20-evidence")),
        WorkspaceSectionPath(section=WorkspaceSection.AUDIT, relative_path=WorkspacePath(value="30-audit")),
    )


def _manifest(**overrides: object):
    from boardroom_os.workspace.manifest import (
        WorkflowRef,
        WorkspaceManifest,
        WorkspaceManifestRef,
        WorkspacePath,
    )

    fields: dict[str, object] = {
        "workspace_manifest_id": WorkspaceManifestRef(value="workspace-manifest.workflow-tiny"),
        "workflow_ref": WorkflowRef(value="workflow-tiny"),
        "workspace_root": WorkspacePath(value="workspace/workflow-tiny"),
        "package_contract_ref": ContractId(value="package-contract.workspace"),
        "sections": _manifest_sections(),
    }
    fields.update(overrides)
    return WorkspaceManifest(**fields)


def test_build_workspace_manifest_creates_canonical_four_section_manifest() -> None:
    from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, WorkspaceSection, build_workspace_manifest

    package_contract = _package_contract(package_root="10-project")

    manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-tiny"),
        workspace_root=WorkspacePath(value="workspace/workflow-tiny"),
        package_contract=package_contract,
    )

    assert manifest.workspace_manifest_id.value == "workspace-manifest.workflow-tiny"
    assert manifest.workflow_ref.value == "workflow-tiny"
    assert manifest.workspace_root.value == "workspace/workflow-tiny"
    assert manifest.package_contract_ref == package_contract.package_contract_id
    assert manifest.boardroom_root.value == "00-boardroom"
    assert manifest.package_root.value == "10-project"
    assert manifest.evidence_root.value == "20-evidence"
    assert manifest.audit_root.value == "30-audit"
    assert manifest.full_section_path(WorkspaceSection.PROJECT).value == "workspace/workflow-tiny/10-project"
    assert [section.section for section in manifest.sections] == [
        WorkspaceSection.BOARDROOM,
        WorkspaceSection.PROJECT,
        WorkspaceSection.EVIDENCE,
        WorkspaceSection.AUDIT,
    ]
    assert [section.relative_path.value for section in manifest.sections] == [
        "00-boardroom",
        "10-project",
        "20-evidence",
        "30-audit",
    ]


def test_workspace_manifest_model_dump_has_stable_auditable_section_order() -> None:
    from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, WorkspaceSection, build_workspace_manifest

    manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-tiny"),
        workspace_root=WorkspacePath(value="workspace/workflow-tiny"),
        package_contract=_package_contract(package_root="10-project"),
    )

    dumped_sections = manifest.model_dump()["sections"]

    assert [section["section"] for section in dumped_sections] == [
        WorkspaceSection.BOARDROOM,
        WorkspaceSection.PROJECT,
        WorkspaceSection.EVIDENCE,
        WorkspaceSection.AUDIT,
    ]
    assert [section["relative_path"]["value"] for section in dumped_sections] == [
        "00-boardroom",
        "10-project",
        "20-evidence",
        "30-audit",
    ]


def test_build_workspace_manifest_is_stable_for_same_inputs() -> None:
    from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, WorkspaceSection, build_workspace_manifest

    package_contract = _package_contract(package_root="10-project")
    workflow_ref = WorkflowRef(value="workflow-tiny")
    workspace_root = WorkspacePath(value="workspace/workflow-tiny")

    first = build_workspace_manifest(
        workflow_ref=workflow_ref,
        workspace_root=workspace_root,
        package_contract=package_contract,
    )
    second = build_workspace_manifest(
        workflow_ref=workflow_ref,
        workspace_root=workspace_root,
        package_contract=package_contract,
    )

    assert second.workspace_manifest_id == first.workspace_manifest_id
    assert second.package_contract_ref == package_contract.package_contract_id
    assert [section.relative_path.value for section in second.sections] == [
        section.relative_path.value for section in first.sections
    ]
    assert second.full_section_path(WorkspaceSection.PROJECT) == first.full_section_path(WorkspaceSection.PROJECT)


def test_workspace_manifest_rejects_missing_project_section() -> None:
    sections = tuple(section for section in _manifest_sections() if section.relative_path.value != "10-project")

    with pytest.raises(_VERIFY_ERRORS, match="project|10-project"):
        _manifest(sections=sections)


def test_workspace_manifest_rejects_missing_evidence_section() -> None:
    sections = tuple(section for section in _manifest_sections() if section.relative_path.value != "20-evidence")

    with pytest.raises(_VERIFY_ERRORS, match="evidence|20-evidence"):
        _manifest(sections=sections)


@pytest.mark.parametrize("package_root", ["/tmp/project", "../10-project", "project", "10-project/src"])
def test_build_workspace_manifest_rejects_package_root_outside_workspace(package_root: str) -> None:
    from boardroom_os.workspace.manifest import WorkflowRef, WorkspaceManifestError, WorkspacePath, build_workspace_manifest

    with pytest.raises(WorkspaceManifestError, match="package root"):
        build_workspace_manifest(
            workflow_ref=WorkflowRef(value="workflow-tiny"),
            workspace_root=WorkspacePath(value="workspace/workflow-tiny"),
            package_contract=_package_contract(package_root=package_root),
        )


@pytest.mark.parametrize(
    ("section_name", "bad_path", "expected_path"),
    [
        ("project", "project", "10-project"),
        ("project", "src", "10-project"),
        ("project", "src/boardroom_os", "10-project"),
        ("evidence", "evidence", "20-evidence"),
        ("evidence", "10-project/evidence", "20-evidence"),
        ("audit", "audit", "30-audit"),
        ("boardroom", "boardroom", "00-boardroom"),
    ],
)
def test_workspace_section_path_rejects_non_canonical_section_paths(
    section_name: str, bad_path: str, expected_path: str
) -> None:
    from boardroom_os.workspace.manifest import WorkspacePath, WorkspaceSection, WorkspaceSectionPath

    with pytest.raises(_VERIFY_ERRORS, match=f"{section_name}|{expected_path}"):
        WorkspaceSectionPath(
            section=WorkspaceSection(section_name),
            relative_path=WorkspacePath(value=bad_path),
        )


@pytest.mark.parametrize(
    ("section_name", "relative_path"),
    [
        ("cache", "40-cache"),
        ("tmp", "tmp/scratch"),
        ("scratch", "scratch"),
        ("build-cache", "build-cache"),
        ("secrets", "secrets"),
        ("runtime-scratch", "runtime-scratch"),
    ],
)
def test_workspace_section_path_rejects_non_canonical_durable_sections(
    section_name: str, relative_path: str
) -> None:
    from boardroom_os.workspace.manifest import WorkspacePath, WorkspaceSectionPath

    with pytest.raises(_VERIFY_ERRORS, match="boardroom|project|evidence|audit"):
        WorkspaceSectionPath(section=section_name, relative_path=WorkspacePath(value=relative_path))


def test_workspace_manifest_rejects_duplicate_sections() -> None:
    sections = _manifest_sections()

    with pytest.raises(_VERIFY_ERRORS, match="project|unique|10-project"):
        _manifest(sections=sections + (sections[1],))


@pytest.mark.parametrize(
    "bad_path",
    [
        "/workspace/workflow-tiny",
        "C:/workspace/workflow-tiny",
        "../workspace/workflow-tiny",
        "workspace/../workflow-tiny",
        ".",
        "./workspace",
        "workspace\\workflow-tiny",
        "workspace//workflow-tiny",
        "workspace/workflow-tiny/",
    ],
)
def test_workspace_path_rejects_unsafe_or_non_relative_paths(bad_path: str) -> None:
    from boardroom_os.workspace.manifest import WorkspacePath

    with pytest.raises(_VERIFY_ERRORS):
        WorkspacePath(value=bad_path)


@pytest.mark.parametrize(
    "workspace_root",
    [
        "src",
        "src/boardroom_os",
        "src/boardroom_os/workspace",
        "tests",
        "tests/proving",
        "doc",
        "doc/workspace",
        "scripts",
        "examples",
        "backend",
        "backend/app",
    ],
)
def test_workspace_manifest_rejects_workspace_root_inside_framework_layout(workspace_root: str) -> None:
    from boardroom_os.workspace.manifest import WorkspacePath

    with pytest.raises(_VERIFY_ERRORS, match="workspace_root|framework|reserved"):
        _manifest(workspace_root=WorkspacePath(value=workspace_root))


def test_workspace_manifest_rejects_manifest_id_that_does_not_match_workflow_ref() -> None:
    from boardroom_os.workspace.manifest import WorkspaceManifestRef

    with pytest.raises(_VERIFY_ERRORS, match="workspace_manifest_id|workflow_ref|workspace-manifest.workflow-tiny"):
        _manifest(workspace_manifest_id=WorkspaceManifestRef(value="workspace-manifest.other-workflow"))


def test_workspace_section_path_rejects_extra_fields() -> None:
    from boardroom_os.workspace.manifest import WorkspacePath, WorkspaceSection, WorkspaceSectionPath

    with pytest.raises(ValidationError, match="Extra|extra|not permitted"):
        WorkspaceSectionPath(
            section=WorkspaceSection.PROJECT,
            relative_path=WorkspacePath(value="10-project"),
            unexpected_field="not allowed",
        )


def test_workspace_manifest_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError, match="Extra|extra|not permitted"):
        _manifest(unexpected_field="not allowed")
