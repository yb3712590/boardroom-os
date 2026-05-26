from __future__ import annotations

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
from boardroom_os.evidence.verifier import VerifiedEvidenceRef
from boardroom_os.execution.context_index import ProviderAttemptRef
from boardroom_os.graph.ticket import TicketId
from boardroom_os.workspace.assembler import (
    PackageArtifact,
    PackageArtifactKind,
    PackageArtifactPath,
    assemble_package,
)
from boardroom_os.workspace.manifest import WorkflowRef, WorkspacePath, build_workspace_manifest
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceLineageRecord,
    build_source_inventory,
)


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.source-inventory-happy"),
        project_charter_ref=ContractId(value="project.charter.source-inventory-happy"),
        template_kind=template_kind,
        documentation_density=DocumentationDensity.STANDARD,
        docs_template_key=docs_template_key_for(template_kind),
        documentation_obligations=default_documentation_obligations_for(template_kind),
    )


def _surface(surface_ref: str, paths: tuple[str, ...], acceptance_refs: tuple[str, ...]) -> SourceSurface:
    return SourceSurface(
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        name=surface_ref.replace("-", " ").title(),
        paths=paths,
        owned_by=OwnerSeatRef(value="worker-source-inventory"),
        acceptance_refs=tuple(AcceptanceRef(value=ref) for ref in acceptance_refs),
        required_tests=(RequiredTestRef(value="pytest-source-inventory"),),
    )


def _command(command_id: str) -> PackageCommand:
    return PackageCommand(
        command_id=ContractId(value=command_id),
        label=command_id,
        command=("python", "-m", "pytest"),
        cwd=".",
    )


def _package_contract():
    profile = _profile()
    return create_package_contract(
        methodology_registry=MethodologyProfileRegistry.from_profiles(profile),
        package_contract_id=ContractId(value="package-contract.source-inventory-happy"),
        project_charter_ref=ContractId(value="project.charter.source-inventory-happy"),
        package_root="10-project",
        project_type=PackageProjectType.SOFTWARE,
        source_surfaces=(
            _surface("backend-api", ("backend/",), ("AC-BACKEND",)),
            _surface("frontend-ui", ("frontend/",), ("AC-FRONTEND",)),
            _surface("package-tests", ("tests/",), ("AC-TESTS",)),
            _surface("run-manifest", ("run-manifest.json",), ("AC-RUN",)),
            _surface("project-docs", ("docs/",), ("AC-DOCS",)),
        ),
        run_commands=(_command("run-source-inventory"),),
        test_commands=(_command("test-source-inventory"),),
        integration_boundaries=(IntegrationBoundary(value="local-http-api"),),
        docs_required=True,
        closeout_required=True,
        methodology_profile_ref=profile.methodology_profile_id,
        docs_template_key=profile.docs_template_key,
        documentation_obligations=profile.documentation_obligations,
    )


def _artifact(
    relative_path: str,
    kind: PackageArtifactKind,
    surface_ref: str = "backend-api",
    acceptance_ref: str = "AC-BACKEND",
) -> PackageArtifact:
    if kind in {PackageArtifactKind.README, PackageArtifactKind.AGENTS}:
        return PackageArtifact(
            relative_path=PackageArtifactPath(value=relative_path),
            artifact_kind=kind,
        )
    return PackageArtifact(
        relative_path=PackageArtifactPath(value=relative_path),
        artifact_kind=kind,
        source_surface_refs=(SourceSurfaceRef(value=surface_ref),),
        acceptance_refs=(AcceptanceRef(value=acceptance_ref),),
    )


def _package_assembly(package_contract):
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-source-inventory-happy"),
        workspace_root=WorkspacePath(value="workspace/workflow-source-inventory-happy"),
        package_contract=package_contract,
    )
    return assemble_package(
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
        artifacts=(
            _artifact("README.md", PackageArtifactKind.README),
            _artifact("AGENTS.md", PackageArtifactKind.AGENTS),
            _artifact("package-contract.json", PackageArtifactKind.PACKAGE_CONTRACT),
            _artifact("run-manifest.json", PackageArtifactKind.RUN_MANIFEST, "run-manifest", "AC-RUN"),
            _artifact("backend/app.py", PackageArtifactKind.SOURCE, "backend-api", "AC-BACKEND"),
            _artifact("frontend/App.tsx", PackageArtifactKind.SOURCE, "frontend-ui", "AC-FRONTEND"),
            _artifact("tests/test_app.py", PackageArtifactKind.TEST, "package-tests", "AC-TESTS"),
            _artifact("docs/usage.md", PackageArtifactKind.DOC, "project-docs", "AC-DOCS"),
        ),
    )


def _source_file(path: str, sha: str) -> SourceFileRecord:
    return SourceFileRecord(path=SourceFilePath(value=path), sha256=sha)


def _lineage(path: str, surface_ref: str, acceptance_ref: str) -> SourceLineageRecord:
    normalized = path.replace("/", ".").replace("_", "-")
    producer_ticket_ref = TicketId(value=f"ticket.{normalized}")
    return SourceLineageRecord(
        path=SourceFilePath(value=path),
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        producer_ticket_ref=producer_ticket_ref,
        producer_attempt_ref=ProviderAttemptRef(value=f"provider-attempt.{normalized}.1"),
        consumer_ticket_refs=(producer_ticket_ref,),
        acceptance_refs=(AcceptanceRef(value=acceptance_ref),),
        evidence_refs=(VerifiedEvidenceRef(value=f"verified-evidence.{normalized}"),),
    )


def test_source_inventory_builds_deterministic_lineage_for_package_files() -> None:
    package_contract = _package_contract()
    package_assembly = _package_assembly(package_contract)

    inventory = build_source_inventory(
        package_assembly=package_assembly,
        package_contract=package_contract,
        package_commit_ref=PackageCommitRef(value="commit.source-inventory-happy"),
        source_files=(
            _source_file("tests/test_app.py", "c" * 64),
            _source_file("backend/app.py", "a" * 64),
            _source_file("docs/usage.md", "d" * 64),
            _source_file("frontend/App.tsx", "b" * 64),
        ),
        lineage_records=(
            _lineage("frontend/App.tsx", "frontend-ui", "AC-FRONTEND"),
            _lineage("docs/usage.md", "project-docs", "AC-DOCS"),
            _lineage("backend/app.py", "backend-api", "AC-BACKEND"),
            _lineage("tests/test_app.py", "package-tests", "AC-TESTS"),
        ),
    )

    assert inventory.source_inventory_id.value == (
        f"source-inventory.{package_assembly.package_assembly_id.value}.commit.source-inventory-happy"
    )
    assert inventory.package_assembly_ref == package_assembly.package_assembly_id
    assert inventory.package_contract_ref == package_contract.package_contract_id
    assert inventory.package_commit_ref == PackageCommitRef(value="commit.source-inventory-happy")
    assert inventory.package_root.value == "10-project"
    assert tuple(entry.path.value for entry in inventory.entries) == (
        "backend/app.py",
        "docs/usage.md",
        "frontend/App.tsx",
        "tests/test_app.py",
    )
    assert tuple(entry.sha256.value for entry in inventory.entries) == (
        "a" * 64,
        "d" * 64,
        "b" * 64,
        "c" * 64,
    )
    assert inventory.entries[0].producer_ticket_ref == TicketId(value="ticket.backend.app.py")
    assert inventory.entries[0].producer_attempt_ref == ProviderAttemptRef(value="provider-attempt.backend.app.py.1")
    assert inventory.entries[0].consumer_ticket_refs == (TicketId(value="ticket.backend.app.py"),)
    assert inventory.entries[0].evidence_refs == (VerifiedEvidenceRef(value="verified-evidence.backend.app.py"),)


def test_source_inventory_model_dump_is_audit_friendly() -> None:
    package_contract = _package_contract()
    package_assembly = _package_assembly(package_contract)
    inventory = build_source_inventory(
        package_assembly=package_assembly,
        package_contract=package_contract,
        package_commit_ref=PackageCommitRef(value="commit.source-inventory-happy"),
        source_files=(
            _source_file("backend/app.py", "a" * 64),
            _source_file("frontend/App.tsx", "b" * 64),
            _source_file("tests/test_app.py", "c" * 64),
            _source_file("docs/usage.md", "d" * 64),
        ),
        lineage_records=(
            _lineage("backend/app.py", "backend-api", "AC-BACKEND"),
            _lineage("frontend/App.tsx", "frontend-ui", "AC-FRONTEND"),
            _lineage("tests/test_app.py", "package-tests", "AC-TESTS"),
            _lineage("docs/usage.md", "project-docs", "AC-DOCS"),
        ),
    )

    dumped = inventory.model_dump()

    assert dumped["package_root"] == {"value": "10-project"}
    assert dumped["entries"][0]["path"] == {"value": "backend/app.py"}
    assert dumped["entries"][0]["sha256"] == {"value": "a" * 64}
    assert dumped["entries"][0]["producer_ticket_ref"] == {"value": "ticket.backend.app.py"}
    assert dumped["entries"][0]["producer_attempt_ref"] == {"value": "provider-attempt.backend.app.py.1"}
    assert dumped["entries"][0]["consumer_ticket_refs"] == [{"value": "ticket.backend.app.py"}]
    assert dumped["entries"][0]["acceptance_refs"] == [{"value": "AC-BACKEND"}]
    assert dumped["entries"][0]["evidence_refs"] == [{"value": "verified-evidence.backend.app.py"}]
