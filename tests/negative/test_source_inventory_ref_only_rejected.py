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

_VERIFY_ERRORS = (ValueError, ValidationError)
_SHA = "a" * 64


def _profile() -> MethodologyProfile:
    template_kind = MethodologyTemplateKind.HYBRID
    return MethodologyProfile(
        methodology_profile_id=ContractId(value="methodology-profile.source-inventory"),
        project_charter_ref=ContractId(value="project.charter.source-inventory"),
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
        package_contract_id=ContractId(value="package-contract.source-inventory"),
        project_charter_ref=ContractId(value="project.charter.source-inventory"),
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



def _package_assembly():
    package_contract = _package_contract()
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-source-inventory"),
        workspace_root=WorkspacePath(value="workspace/workflow-source-inventory"),
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



def _source_file(path: str = "backend/app.py", sha256: str = _SHA):
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceFileRecord

    return SourceFileRecord(path=SourceFilePath(value=path), sha256=sha256)



def _lineage(
    path: str = "backend/app.py",
    surface_ref: str = "backend-api",
    acceptance_ref: str = "AC-BACKEND",
    *,
    consumer_ticket_refs: tuple[TicketId, ...],
    producer_ticket_ref: TicketId | None = None,
    producer_attempt_ref: ProviderAttemptRef | None = None,
    acceptance_refs: tuple[AcceptanceRef, ...] | None = None,
    evidence_refs: tuple[VerifiedEvidenceRef, ...] | None = None,
):
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    producer_ref = producer_ticket_ref or TicketId(value="ticket.backend")
    return SourceLineageRecord(
        path=SourceFilePath(value=path),
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        producer_ticket_ref=producer_ref,
        producer_attempt_ref=producer_attempt_ref or ProviderAttemptRef(value="provider-attempt.backend.1"),
        consumer_ticket_refs=consumer_ticket_refs,
        acceptance_refs=acceptance_refs or (AcceptanceRef(value=acceptance_ref),),
        evidence_refs=evidence_refs or (VerifiedEvidenceRef(value="verified-evidence.backend"),),
    )



def _build(*, source_files=None, lineage_records=None, package_commit_ref="commit.source-inventory"):
    from boardroom_os.workspace.source_inventory import PackageCommitRef, build_source_inventory

    return build_source_inventory(
        package_assembly=_package_assembly(),
        package_contract=_package_contract(),
        package_commit_ref=PackageCommitRef(value=package_commit_ref),
        source_files=source_files if source_files is not None else (_source_file(),),
        lineage_records=lineage_records
        if lineage_records is not None
        else (_lineage(consumer_ticket_refs=(TicketId(value="ticket.backend"),)),),
    )



def test_source_inventory_rejects_ref_only_package_assembly() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="source files|lineage|ref-only"):
        _build(source_files=(), lineage_records=())



def test_source_inventory_rejects_source_file_without_sha256() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceFileRecord

    with pytest.raises(_VERIFY_ERRORS, match="sha256|Field required"):
        SourceFileRecord.model_validate({"path": SourceFilePath(value="backend/app.py")})



def test_source_inventory_rejects_malformed_sha256() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="sha256"):
        _source_file(sha256="ABC")



def test_source_inventory_rejects_lineage_without_producer_ticket_ref() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="producer_ticket_ref|Field required"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "consumer_ticket_refs": (TicketId(value="ticket.backend"),),
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )



def test_source_inventory_rejects_lineage_without_producer_attempt_ref() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="producer_attempt_ref|Field required"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "consumer_ticket_refs": (TicketId(value="ticket.backend"),),
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )



def test_source_inventory_rejects_lineage_without_consumer_ticket_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="consumer_ticket_refs|Field required"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )



def test_source_inventory_rejects_lineage_without_acceptance_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="acceptance refs|Field required"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "consumer_ticket_refs": (TicketId(value="ticket.backend"),),
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )



def test_source_inventory_rejects_lineage_without_evidence_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="evidence refs|Field required"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "consumer_ticket_refs": (TicketId(value="ticket.backend"),),
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
            }
        )


def test_source_inventory_hash_is_stable_when_lineage_refs_are_reordered() -> None:
    from boardroom_os.audit.git_version_audit import source_inventory_hash
    from boardroom_os.workspace.assembler import PackageAssembly, PackageAssemblyRef
    from boardroom_os.workspace.manifest import WorkspaceManifestRef

    assembly = PackageAssembly(
        package_assembly_id=PackageAssemblyRef(value="package-assembly.hash-stability"),
        workspace_manifest_ref=WorkspaceManifestRef(value="workspace-manifest.hash-stability"),
        package_contract_ref=ContractId(value="package-contract.source-inventory"),
        package_root=WorkspacePath(value="10-project"),
        artifacts=(
            _artifact("backend/app.py", PackageArtifactKind.SOURCE, "backend-api", "AC-BACKEND"),
        ),
    )

    def build_with_order(
        consumer_ticket_refs: tuple[TicketId, ...],
        evidence_refs: tuple[VerifiedEvidenceRef, ...],
    ):
        from boardroom_os.workspace.source_inventory import PackageCommitRef, build_source_inventory

        return build_source_inventory(
            package_assembly=assembly,
            package_contract=_package_contract(),
            package_commit_ref=PackageCommitRef(value="commit.source-inventory"),
            source_files=(_source_file(),),
            lineage_records=(
                _lineage(
                    consumer_ticket_refs=consumer_ticket_refs,
                    evidence_refs=evidence_refs,
                ),
            ),
        )

    first = build_with_order(
        (
            TicketId(value="ticket.backend.z"),
            TicketId(value="ticket.backend.a"),
        ),
        (
            VerifiedEvidenceRef(value="verified-evidence.z"),
            VerifiedEvidenceRef(value="verified-evidence.a"),
        ),
    )
    second = build_with_order(
        (
            TicketId(value="ticket.backend.a"),
            TicketId(value="ticket.backend.z"),
        ),
        (
            VerifiedEvidenceRef(value="verified-evidence.a"),
            VerifiedEvidenceRef(value="verified-evidence.z"),
        ),
    )

    assert first.entries[0].consumer_ticket_refs == second.entries[0].consumer_ticket_refs
    assert first.entries[0].acceptance_refs == second.entries[0].acceptance_refs
    assert first.entries[0].evidence_refs == second.entries[0].evidence_refs
    assert source_inventory_hash(first) == source_inventory_hash(second)



def test_source_inventory_rejects_lineage_with_empty_consumer_ticket_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="consumer ticket refs must not be empty"):
        SourceLineageRecord(
            path=SourceFilePath(value="backend/app.py"),
            source_surface_ref=SourceSurfaceRef(value="backend-api"),
            producer_ticket_ref=TicketId(value="ticket.backend"),
            producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend.1"),
            consumer_ticket_refs=(),
            acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
            evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.backend"),),
        )



def test_source_inventory_rejects_duplicate_consumer_ticket_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="consumer ticket refs must be unique"):
        SourceLineageRecord(
            path=SourceFilePath(value="backend/app.py"),
            source_surface_ref=SourceSurfaceRef(value="backend-api"),
            producer_ticket_ref=TicketId(value="ticket.backend"),
            producer_attempt_ref=ProviderAttemptRef(value="provider-attempt.backend.1"),
            consumer_ticket_refs=(TicketId(value="ticket.backend"), TicketId(value="ticket.backend")),
            acceptance_refs=(AcceptanceRef(value="AC-BACKEND"),),
            evidence_refs=(VerifiedEvidenceRef(value="verified-evidence.backend"),),
        )


@pytest.mark.parametrize(
    ("field_name", "duplicate_values", "expected_message"),
    (
        (
            "acceptance_refs",
            (AcceptanceRef(value="AC-BACKEND"), AcceptanceRef(value="AC-BACKEND")),
            "acceptance refs must be unique",
        ),
        (
            "evidence_refs",
            (
                VerifiedEvidenceRef(value="verified-evidence.backend"),
                VerifiedEvidenceRef(value="verified-evidence.backend"),
            ),
            "evidence refs must be unique",
        ),
    ),
)
def test_source_inventory_rejects_duplicate_lineage_tuple_refs(
    field_name: str,
    duplicate_values: tuple[object, object],
    expected_message: str,
) -> None:
    with pytest.raises(_VERIFY_ERRORS, match=expected_message):
        _lineage(
            consumer_ticket_refs=(TicketId(value="ticket.backend"),),
            **{field_name: duplicate_values},
        )


@pytest.mark.parametrize(
    "bad_path",
    [
        "/tmp/app.py",
        "../app.py",
        "backend\\app.py",
        "10-project/backend/app.py",
        "20-evidence/source.json",
        "30-audit/process-audit.md",
        "src/boardroom_os/runtime.py",
        "doc/source.md",
        "scripts/build.py",
        "examples/demo.py",
    ],
)
def test_source_file_path_rejects_paths_outside_package_root_or_framework_paths(bad_path: str) -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath

    with pytest.raises(_VERIFY_ERRORS, match="source file path|package root|framework|relative|parent"):
        SourceFilePath(value=bad_path)


def test_source_inventory_rejects_duplicate_source_file_paths() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="source file paths must be unique"):
        _build(source_files=(_source_file(), _source_file()), lineage_records=(_lineage(consumer_ticket_refs=(TicketId(value="ticket.backend"),)),))


def test_source_inventory_rejects_duplicate_lineage_paths() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="lineage paths must be unique"):
        _build(source_files=(_source_file(),), lineage_records=(_lineage(consumer_ticket_refs=(TicketId(value="ticket.backend"),)), _lineage(consumer_ticket_refs=(TicketId(value="ticket.backend"),))))


def test_source_inventory_rejects_source_file_missing_lineage() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="missing lineage"):
        _build(
            source_files=(_source_file("backend/app.py"),),
            lineage_records=(_lineage("frontend/App.tsx", "frontend-ui", "AC-FRONTEND", consumer_ticket_refs=(TicketId(value="ticket.backend"),)),),
        )


def test_source_inventory_rejects_lineage_for_unknown_source_file() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="lineage path is missing source file"):
        _build(
            source_files=(_source_file("backend/app.py"),),
            lineage_records=(
                _lineage("backend/app.py", consumer_ticket_refs=(TicketId(value="ticket.backend"),)),
                _lineage("frontend/App.tsx", "frontend-ui", "AC-FRONTEND", consumer_ticket_refs=(TicketId(value="ticket.backend"),)),
            ),
        )


def test_source_inventory_rejects_lineage_path_not_in_package_assembly() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="lineage path is not in package assembly"):
        _build(
            source_files=(_source_file("backend/ghost.py"),),
            lineage_records=(_lineage("backend/ghost.py", consumer_ticket_refs=(TicketId(value="ticket.backend"),)),),
        )


def test_source_inventory_rejects_missing_implementation_bearing_artifact_entry() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="missing source inventory entry"):
        _build(source_files=(_source_file("backend/app.py"),), lineage_records=(_lineage("backend/app.py", consumer_ticket_refs=(TicketId(value="ticket.backend"),)),))


def test_source_inventory_rejects_unknown_source_surface_ref() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="unknown source surface"):
        _build(source_files=(_source_file(),), lineage_records=(_lineage(surface_ref="unknown-surface", consumer_ticket_refs=(TicketId(value="ticket.backend"),)),))


def test_source_inventory_rejects_acceptance_ref_outside_source_surface() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="acceptance refs outside source surface"):
        _build(source_files=(_source_file(),), lineage_records=(_lineage(acceptance_ref="AC-FRONTEND", consumer_ticket_refs=(TicketId(value="ticket.backend"),)),))


def test_source_inventory_rejects_source_surface_not_compatible_with_package_artifact() -> None:
    with pytest.raises(_VERIFY_ERRORS, match="source surface is not compatible"):
        _build(
            source_files=(_source_file("backend/app.py"),),
            lineage_records=(_lineage("backend/app.py", "frontend-ui", "AC-FRONTEND", consumer_ticket_refs=(TicketId(value="ticket.backend"),)),),
        )


def test_source_inventory_rejects_acceptance_refs_that_do_not_cover_package_artifact() -> None:
    from boardroom_os.workspace.source_inventory import PackageCommitRef, build_source_inventory

    package_contract = _package_contract()
    backend_surface = next(
        surface
        for surface in package_contract.source_surfaces
        if surface.source_surface_ref.value == "backend-api"
    )
    expanded_backend_surface = backend_surface.model_copy(
        update={
            "acceptance_refs": (
                AcceptanceRef(value="AC-BACKEND"),
                AcceptanceRef(value="AC-OTHER"),
            )
        }
    )
    expanded_contract = package_contract.model_copy(
        update={
            "source_surfaces": tuple(
                expanded_backend_surface
                if surface.source_surface_ref.value == "backend-api"
                else surface
                for surface in package_contract.source_surfaces
            )
        }
    )

    with pytest.raises(_VERIFY_ERRORS, match="acceptance refs do not cover package artifact"):
        build_source_inventory(
            package_assembly=_package_assembly(),
            package_contract=expanded_contract,
            package_commit_ref=PackageCommitRef(value="commit.source-inventory"),
            source_files=(_source_file("backend/app.py"),),
            lineage_records=(_lineage("backend/app.py", "backend-api", "AC-OTHER", consumer_ticket_refs=(TicketId(value="ticket.backend"),)),),
        )


def test_source_inventory_rejects_package_contract_mismatch() -> None:
    from boardroom_os.workspace.source_inventory import PackageCommitRef, build_source_inventory

    package_contract = _package_contract()
    other_contract = package_contract.model_copy(
        update={"package_contract_id": ContractId(value="package-contract.other")}
    )

    with pytest.raises(_VERIFY_ERRORS, match="package_contract_ref"):
        build_source_inventory(
            package_assembly=_package_assembly(),
            package_contract=other_contract,
            package_commit_ref=PackageCommitRef(value="commit.source-inventory"),
            source_files=(_source_file(),),
            lineage_records=(_lineage(consumer_ticket_refs=(TicketId(value="ticket.backend"),)),),
        )


def test_source_inventory_rejects_empty_package_commit_ref() -> None:
    from boardroom_os.workspace.source_inventory import PackageCommitRef

    with pytest.raises(_VERIFY_ERRORS, match="value must not be empty"):
        PackageCommitRef(value=" ")


def test_source_inventory_models_reject_extra_fields() -> None:
    from boardroom_os.workspace.source_inventory import SourceFileRecord

    with pytest.raises(_VERIFY_ERRORS, match="Extra inputs"):
        SourceFileRecord.model_validate(
            {
                "path": {"value": "backend/app.py"},
                "sha256": {"value": _SHA},
                "unexpected": "field",
            }
        )


def test_source_lineage_record_rejects_scalar_consumer_ticket_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="consumer_ticket_refs must be a tuple or list"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "consumer_ticket_refs": "ticket.backend",
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )



def test_source_lineage_record_rejects_scalar_acceptance_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="acceptance_refs must be a tuple or list"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "consumer_ticket_refs": (TicketId(value="ticket.backend"),),
                "acceptance_refs": "AC-BACKEND",
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )


def test_source_lineage_record_rejects_scalar_evidence_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceLineageRecord

    with pytest.raises(_VERIFY_ERRORS, match="evidence_refs must be a tuple or list"):
        SourceLineageRecord.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "consumer_ticket_refs": (TicketId(value="ticket.backend"),),
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
                "evidence_refs": "verified-evidence.backend",
            }
        )


def test_source_inventory_entry_rejects_scalar_consumer_ticket_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceInventoryEntry

    with pytest.raises(_VERIFY_ERRORS, match="consumer_ticket_refs must be a tuple or list"):
        SourceInventoryEntry.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "sha256": _SHA,
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "consumer_ticket_refs": "ticket.backend",
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )



def test_source_inventory_entry_rejects_scalar_acceptance_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceInventoryEntry

    with pytest.raises(_VERIFY_ERRORS, match="acceptance_refs must be a tuple or list"):
        SourceInventoryEntry.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "sha256": _SHA,
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "consumer_ticket_refs": (TicketId(value="ticket.backend"),),
                "acceptance_refs": "AC-BACKEND",
                "evidence_refs": (VerifiedEvidenceRef(value="verified-evidence.backend"),),
            }
        )


def test_source_inventory_entry_rejects_scalar_evidence_refs() -> None:
    from boardroom_os.workspace.source_inventory import SourceFilePath, SourceInventoryEntry

    with pytest.raises(_VERIFY_ERRORS, match="evidence_refs must be a tuple or list"):
        SourceInventoryEntry.model_validate(
            {
                "path": SourceFilePath(value="backend/app.py"),
                "sha256": _SHA,
                "source_surface_ref": SourceSurfaceRef(value="backend-api"),
                "producer_ticket_ref": TicketId(value="ticket.backend"),
                "producer_attempt_ref": ProviderAttemptRef(value="provider-attempt.backend.1"),
                "consumer_ticket_refs": (TicketId(value="ticket.backend"),),
                "acceptance_refs": (AcceptanceRef(value="AC-BACKEND"),),
                "evidence_refs": "verified-evidence.backend",
            }
        )
