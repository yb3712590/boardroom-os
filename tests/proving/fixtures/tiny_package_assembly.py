from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Mapping

from boardroom_os.adapters.process_runner import (
    CommandRunner,
    CommandRunnerInput,
    CommandRunnerResult,
)
from boardroom_os.contracts.evidence_obligation import EvidenceObligation
from boardroom_os.contracts.package import PackageContract
from boardroom_os.contracts.types import AcceptanceRef, ContractId, SourceSurfaceRef
from boardroom_os.evidence.claim import (
    EvidenceArtifactRef,
    build_evidence_claim_from_verification_run,
)
from boardroom_os.evidence.table import (
    FinalEvidenceTable,
    FinalEvidenceTableBuilder,
    FinalEvidenceTableInput,
)
from boardroom_os.evidence.verifier import (
    ArtifactManifest,
    ArtifactManifestEntry,
    ArtifactSha256,
    EvidencePurposePolicy,
    EvidencePurposeRule,
    EvidenceVerificationInput,
    EvidenceVerifier,
    VerifiedEvidence,
)
from boardroom_os.execution.fallback import EvidencePurpose
from boardroom_os.execution.verification_run import (
    EnvironmentProfileRef,
    RunnerRef,
    WorkspaceSnapshotRef,
)
from boardroom_os.graph.ticket import TicketId
from boardroom_os.providers.attempt import ProviderAttempt
from boardroom_os.workspace.assembler import (
    PackageArtifact,
    PackageArtifactKind,
    PackageArtifactPath,
    PackageAssembly,
    assemble_package,
)
from boardroom_os.workspace.evidence_export import (
    EvidenceBundleArtifactKind,
    WorkspaceEvidenceBundle,
    build_workspace_evidence_bundle,
)
from boardroom_os.workspace.manifest import (
    WorkflowRef,
    WorkspaceManifest,
    WorkspacePath,
    build_workspace_manifest,
)
from boardroom_os.workspace.run_manifest import RunManifest, build_run_manifest
from boardroom_os.workspace.source_inventory import (
    PackageCommitRef,
    SourceFilePath,
    SourceFileRecord,
    SourceInventory,
    SourceLineageRecord,
    build_source_inventory,
)
from tests.proving.fixtures.tiny_provider_attempts import (
    TinyProviderAttemptFixture,
    build_tiny_provider_attempt_fixture,
)
from tests.proving.fixtures.tiny_ticket_graph import (
    TICKET_BACKEND_API_ID,
    TICKET_DOCS_RUN_MANIFEST_ID,
    TICKET_FRONTEND_UI_ID,
    TICKET_TESTS_ID,
)


GENERATED_AT = datetime(2026, 5, 30, 9, 0, tzinfo=UTC)
VERIFIED_AT = datetime(2026, 5, 30, 9, 5, tzinfo=UTC)
COMMAND_STARTED_AT = datetime(2026, 5, 30, 9, 10, tzinfo=UTC)
COMMAND_FINISHED_AT = datetime(2026, 5, 30, 9, 10, 1, tzinfo=UTC)
PACKAGE_COMMIT_REF = PackageCommitRef(value="commit.tiny-package-assembly")

EXPECTED_TINY_PACKAGE_PATHS: tuple[str, ...] = (
    "AGENTS.md",
    "README.md",
    "backend/app.py",
    "backend/db.py",
    "backend/tests/test_api.py",
    "docs/usage.md",
    "frontend/app.js",
    "frontend/index.html",
    "package-contract.json",
    "run-manifest.json",
    "tests/integration/test_frontend_backend.py",
)

TINY_PACKAGE_CONTENTS: Mapping[str, str] = {
    "README.md": "# Tiny Book Availability Tracker\n",
    "AGENTS.md": "Run declared commands from the package root.\n",
    "package-contract.json": '{"package_root":"10-project"}\n',
    "backend/app.py": (
        "BOOKS = []\n\n"
        "def create_book(title):\n"
        "    book = {'title': title, 'state': 'IN_LIBRARY'}\n"
        "    BOOKS.append(book)\n"
        "    return book\n\n"
        "def list_books():\n"
        "    return list(BOOKS)\n\n"
        "def checkout(book):\n"
        "    book['state'] = 'CHECKED_OUT'\n"
        "    return book\n\n"
        "def return_book(book):\n"
        "    book['state'] = 'IN_LIBRARY'\n"
        "    return book\n"
    ),
    "backend/db.py": (
        "def persist_state(book):\n"
        "    return {'title': book['title'], 'state': book['state']}\n"
    ),
    "frontend/index.html": (
        "<!doctype html>\n"
        "<html><body><main id=\"app\"></main><script src=\"app.js\"></script></body></html>\n"
    ),
    "frontend/app.js": (
        "export async function loadBooks(fetchImpl) {\n"
        "  const response = await fetchImpl('/books');\n"
        "  return response.json();\n"
        "}\n"
    ),
    "backend/tests/test_api.py": (
        "from backend.app import checkout, create_book, list_books, return_book\n"
        "from backend.db import persist_state\n\n"
        "def test_backend_api_and_sqlite_persistence_contract():\n"
        "    book = create_book('Dune')\n"
        "    checkout(book)\n"
        "    persisted = persist_state(book)\n"
        "    assert persisted['state'] == 'CHECKED_OUT'\n"
        "    return_book(book)\n"
        "    assert list_books()[0]['state'] == 'IN_LIBRARY'\n"
    ),
    "tests/integration/test_frontend_backend.py": (
        "from pathlib import Path\n\n"
        "def test_frontend_fetches_backend_and_run_manifest_exists():\n"
        "    app_js = Path('frontend/app.js').read_text(encoding='utf-8')\n"
        "    assert \"fetchImpl('/books')\" in app_js\n"
        "    assert Path('run-manifest.json').exists()\n"
    ),
    "docs/usage.md": "Use pytest backend/tests and pytest tests/integration.\n",
}


@dataclass(frozen=True)
class TinyPackageAssemblyFixture:
    provider_fixture: TinyProviderAttemptFixture
    workspace_manifest: WorkspaceManifest
    package_contract: PackageContract
    package_artifacts: tuple[PackageArtifact, ...]
    package_assembly: PackageAssembly
    run_manifest: RunManifest
    package_root_path: Path
    source_contents: Mapping[str, str]
    command_results_by_id: Mapping[str, CommandRunnerResult]
    verified_evidence: tuple[VerifiedEvidence, ...]
    source_inventory: SourceInventory
    final_evidence_table: FinalEvidenceTable
    workspace_evidence_bundle: WorkspaceEvidenceBundle

    @property
    def provider_attempts_by_ticket_id(self) -> Mapping[TicketId, ProviderAttempt]:
        return self.provider_fixture.provider_attempts_by_ticket_id

    @property
    def required_evidence_artifact_kinds(self) -> set[EvidenceBundleArtifactKind]:
        return set(EvidenceBundleArtifactKind)

    @property
    def expected_package_paths(self) -> tuple[str, ...]:
        return EXPECTED_TINY_PACKAGE_PATHS

    def assemble_package(
        self,
        *,
        artifacts: tuple[PackageArtifact, ...],
    ) -> PackageAssembly:
        return assemble_package(
            workspace_manifest=self.workspace_manifest,
            package_contract=self.package_contract,
            artifacts=artifacts,
        )

    def build_source_inventory(
        self,
        *,
        source_files: tuple[SourceFileRecord, ...],
        lineage_records: tuple[SourceLineageRecord, ...],
    ) -> SourceInventory:
        return build_source_inventory(
            package_assembly=self.package_assembly,
            package_contract=self.package_contract,
            package_commit_ref=PACKAGE_COMMIT_REF,
            source_files=source_files,
            lineage_records=lineage_records,
        )


def build_tiny_package_assembly_fixture(
    *,
    package_root: Path,
    package_contents: Mapping[str, str] = TINY_PACKAGE_CONTENTS,
) -> TinyPackageAssemblyFixture:
    provider_fixture = build_tiny_provider_attempt_fixture(use_fake_results=True)
    package_contract = provider_fixture.compiled.ticket_graph_fixture.contracts.package_contract
    workspace_manifest = build_workspace_manifest(
        workflow_ref=WorkflowRef(value="workflow-tiny-package-assembly"),
        workspace_root=WorkspacePath(value="workspace/workflow-tiny-package-assembly"),
        package_contract=package_contract,
    )
    package_artifacts = _package_artifacts()
    package_assembly = assemble_package(
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
        artifacts=package_artifacts,
    )
    run_manifest = build_run_manifest(
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
    )
    contents = _package_contents_with_run_manifest(
        package_contents=package_contents,
        run_manifest=run_manifest,
    )
    _write_ephemeral_tiny_package_for_command_evidence(
        package_root=package_root,
        package_contents=contents,
    )
    _validate_physical_run_manifest(
        package_root=package_root,
        run_manifest=run_manifest,
    )
    command_results_by_id = _command_results_by_id(
        provider_fixture=provider_fixture,
        package_root=package_root,
    )
    verified_evidence = _verified_evidence(
        provider_fixture=provider_fixture,
        command_results_by_id=command_results_by_id,
    )
    source_inventory = build_source_inventory(
        package_assembly=package_assembly,
        package_contract=package_contract,
        package_commit_ref=PACKAGE_COMMIT_REF,
        source_files=_source_files(contents),
        lineage_records=_source_lineage_records(
            provider_fixture=provider_fixture,
            verified_evidence=verified_evidence,
        ),
    )
    final_evidence_table = FinalEvidenceTableBuilder().build(
        FinalEvidenceTableInput(
            active_acceptance_contract=(
                provider_fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
            ),
            verified_evidence=verified_evidence,
            generated_at=GENERATED_AT,
        )
    )
    workspace_evidence_bundle = build_workspace_evidence_bundle(
        workspace_manifest=workspace_manifest,
        package_assembly=package_assembly,
        source_inventory=source_inventory,
        run_manifest=run_manifest,
        verification_runs=tuple(
            result.verification_run for result in command_results_by_id.values()
        ),
        verified_evidence=verified_evidence,
        final_evidence_table=final_evidence_table,
    )
    return TinyPackageAssemblyFixture(
        provider_fixture=provider_fixture,
        workspace_manifest=workspace_manifest,
        package_contract=package_contract,
        package_artifacts=package_artifacts,
        package_assembly=package_assembly,
        run_manifest=run_manifest,
        package_root_path=package_root,
        source_contents=contents,
        command_results_by_id=command_results_by_id,
        verified_evidence=verified_evidence,
        source_inventory=source_inventory,
        final_evidence_table=final_evidence_table,
        workspace_evidence_bundle=workspace_evidence_bundle,
    )


def _package_artifacts() -> tuple[PackageArtifact, ...]:
    return (
        _artifact(
            "README.md",
            PackageArtifactKind.README,
            "docs",
            ("AC-TINY-RUN-TEST-COMMANDS",),
        ),
        _artifact(
            "AGENTS.md",
            PackageArtifactKind.AGENTS,
            "docs",
            ("AC-TINY-RUN-TEST-COMMANDS",),
        ),
        _artifact(
            "package-contract.json",
            PackageArtifactKind.PACKAGE_CONTRACT,
            "docs",
            ("AC-TINY-RUN-TEST-COMMANDS",),
        ),
        _artifact(
            "run-manifest.json",
            PackageArtifactKind.RUN_MANIFEST,
            "run-manifest",
            ("AC-TINY-RUN-TEST-COMMANDS",),
        ),
        _artifact(
            "backend/app.py",
            PackageArtifactKind.SOURCE,
            "backend-api",
            (
                "AC-TINY-API-BOOK-CREATE",
                "AC-TINY-API-BOOK-LIST",
                "AC-TINY-API-CHECKOUT-RETURN",
            ),
        ),
        _artifact(
            "backend/db.py",
            PackageArtifactKind.SOURCE,
            "persistence",
            ("AC-TINY-PERSISTENCE-SQLITE",),
        ),
        _artifact(
            "frontend/index.html",
            PackageArtifactKind.SOURCE,
            "frontend-ui",
            ("AC-TINY-UI-FETCH-BACKEND",),
        ),
        _artifact(
            "frontend/app.js",
            PackageArtifactKind.SOURCE,
            "frontend-ui",
            ("AC-TINY-UI-FETCH-BACKEND",),
        ),
        _artifact(
            "backend/tests/test_api.py",
            PackageArtifactKind.TEST,
            "tests",
            (
                "AC-TINY-API-BOOK-CREATE",
                "AC-TINY-API-BOOK-LIST",
                "AC-TINY-API-CHECKOUT-RETURN",
                "AC-TINY-PERSISTENCE-SQLITE",
            ),
        ),
        _artifact(
            "tests/integration/test_frontend_backend.py",
            PackageArtifactKind.TEST,
            "tests",
            (
                "AC-TINY-UI-FETCH-BACKEND",
                "AC-TINY-RUN-TEST-COMMANDS",
            ),
        ),
        _artifact(
            "docs/usage.md",
            PackageArtifactKind.DOC,
            "docs",
            ("AC-TINY-RUN-TEST-COMMANDS",),
        ),
    )


def _artifact(
    relative_path: str,
    artifact_kind: PackageArtifactKind,
    source_surface_ref: str | None = None,
    acceptance_refs: tuple[str, ...] = (),
) -> PackageArtifact:
    if artifact_kind in {PackageArtifactKind.README, PackageArtifactKind.AGENTS}:
        if source_surface_ref is not None:
            return PackageArtifact(
                relative_path=PackageArtifactPath(value=relative_path),
                artifact_kind=artifact_kind,
                source_surface_refs=(SourceSurfaceRef(value=source_surface_ref),),
                acceptance_refs=tuple(AcceptanceRef(value=value) for value in acceptance_refs),
            )
        return PackageArtifact(
            relative_path=PackageArtifactPath(value=relative_path),
            artifact_kind=artifact_kind,
        )
    if source_surface_ref is None:
        raise ValueError("source_surface_ref is required for implementation artifacts")
    return PackageArtifact(
        relative_path=PackageArtifactPath(value=relative_path),
        artifact_kind=artifact_kind,
        source_surface_refs=(SourceSurfaceRef(value=source_surface_ref),),
        acceptance_refs=tuple(AcceptanceRef(value=value) for value in acceptance_refs),
    )


def _source_files(package_contents: Mapping[str, str]) -> tuple[SourceFileRecord, ...]:
    return tuple(
        SourceFileRecord(
            path=SourceFilePath(value=path),
            sha256=_sha256(package_contents[path]),
        )
        for path in (
            "backend/app.py",
            "backend/db.py",
            "backend/tests/test_api.py",
            "docs/usage.md",
            "frontend/app.js",
            "frontend/index.html",
            "tests/integration/test_frontend_backend.py",
        )
    )


def _source_lineage_records(
    *,
    provider_fixture: TinyProviderAttemptFixture,
    verified_evidence: tuple[VerifiedEvidence, ...],
) -> tuple[SourceLineageRecord, ...]:
    evidence_refs_by_type = _evidence_refs_by_artifact_type(verified_evidence)
    return (
        _lineage(
            path="backend/app.py",
            surface_ref="backend-api",
            producer_ticket_ref=TICKET_BACKEND_API_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_BACKEND_API_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_BACKEND_API_ID, TICKET_TESTS_ID),
            acceptance_refs=(
                "AC-TINY-API-BOOK-CREATE",
                "AC-TINY-API-BOOK-LIST",
                "AC-TINY-API-CHECKOUT-RETURN",
            ),
            evidence_refs=evidence_refs_by_type["backend_source_inventory"],
        ),
        _lineage(
            path="backend/db.py",
            surface_ref="persistence",
            producer_ticket_ref=TICKET_BACKEND_API_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_BACKEND_API_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_BACKEND_API_ID, TICKET_TESTS_ID),
            acceptance_refs=("AC-TINY-PERSISTENCE-SQLITE",),
            evidence_refs=evidence_refs_by_type["backend_source_inventory"],
        ),
        _lineage(
            path="frontend/app.js",
            surface_ref="frontend-ui",
            producer_ticket_ref=TICKET_FRONTEND_UI_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_FRONTEND_UI_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_FRONTEND_UI_ID, TICKET_TESTS_ID),
            acceptance_refs=("AC-TINY-UI-FETCH-BACKEND",),
            evidence_refs=evidence_refs_by_type["frontend_source_inventory"],
        ),
        _lineage(
            path="frontend/index.html",
            surface_ref="frontend-ui",
            producer_ticket_ref=TICKET_FRONTEND_UI_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_FRONTEND_UI_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_FRONTEND_UI_ID, TICKET_TESTS_ID),
            acceptance_refs=("AC-TINY-UI-FETCH-BACKEND",),
            evidence_refs=evidence_refs_by_type["frontend_source_inventory"],
        ),
        _lineage(
            path="backend/tests/test_api.py",
            surface_ref="tests",
            producer_ticket_ref=TICKET_TESTS_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_TESTS_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_TESTS_ID,),
            acceptance_refs=(
                "AC-TINY-API-BOOK-CREATE",
                "AC-TINY-API-BOOK-LIST",
                "AC-TINY-API-CHECKOUT-RETURN",
                "AC-TINY-PERSISTENCE-SQLITE",
            ),
            evidence_refs=(
                *evidence_refs_by_type["api_test_run"],
                *evidence_refs_by_type["sqlite_persistence_evidence"],
            ),
        ),
        _lineage(
            path="tests/integration/test_frontend_backend.py",
            surface_ref="tests",
            producer_ticket_ref=TICKET_TESTS_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_TESTS_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_TESTS_ID,),
            acceptance_refs=(
                "AC-TINY-UI-FETCH-BACKEND",
                "AC-TINY-RUN-TEST-COMMANDS",
            ),
            evidence_refs=(
                *evidence_refs_by_type["frontend_backend_integration_evidence"],
                *evidence_refs_by_type["command_evidence"],
            ),
        ),
        _lineage(
            path="docs/usage.md",
            surface_ref="docs",
            producer_ticket_ref=TICKET_DOCS_RUN_MANIFEST_ID,
            producer_attempt_ref=provider_fixture.provider_attempts_by_ticket_id[
                TICKET_DOCS_RUN_MANIFEST_ID
            ].provider_attempt_id,
            consumer_ticket_refs=(TICKET_DOCS_RUN_MANIFEST_ID,),
            acceptance_refs=("AC-TINY-RUN-TEST-COMMANDS",),
            evidence_refs=evidence_refs_by_type["run_manifest"],
        ),
    )


def _lineage(
    *,
    path: str,
    surface_ref: str,
    producer_ticket_ref: TicketId,
    producer_attempt_ref,
    consumer_ticket_refs: tuple[TicketId, ...],
    acceptance_refs: tuple[str, ...],
    evidence_refs: tuple[object, ...],
) -> SourceLineageRecord:
    return SourceLineageRecord(
        path=SourceFilePath(value=path),
        source_surface_ref=SourceSurfaceRef(value=surface_ref),
        producer_ticket_ref=producer_ticket_ref,
        producer_attempt_ref=producer_attempt_ref,
        consumer_ticket_refs=consumer_ticket_refs,
        acceptance_refs=tuple(AcceptanceRef(value=value) for value in acceptance_refs),
        evidence_refs=evidence_refs,
    )


def _command_results_by_id(
    *,
    provider_fixture: TinyProviderAttemptFixture,
    package_root: Path,
) -> dict[str, CommandRunnerResult]:
    execution_package = provider_fixture.execution_packages[TICKET_TESTS_ID]
    package_contract = provider_fixture.compiled.ticket_graph_fixture.contracts.package_contract
    runner = CommandRunner(
        clock=SequenceClock(
            COMMAND_STARTED_AT,
            COMMAND_FINISHED_AT,
            COMMAND_STARTED_AT,
            COMMAND_FINISHED_AT,
        )
    )
    results: dict[str, CommandRunnerResult] = {}
    for command_id in ("test-backend", "test-integration"):
        results[command_id] = runner.run(
            CommandRunnerInput(
                execution_package=execution_package,
                package_contract=package_contract,
                command_id=ContractId(value=command_id),
                package_root=package_root,
                runner_ref=RunnerRef(value="runner.tiny-package-assembly"),
                environment_profile_ref=EnvironmentProfileRef(
                    value="env.tiny-package-assembly"
                ),
                workspace_snapshot_ref=WorkspaceSnapshotRef(
                    value="workspace-snapshot.tiny-package-assembly"
                ),
            )
        )
    return results


class SequenceClock:
    def __init__(self, *timestamps: datetime) -> None:
        self._timestamps = list(timestamps)

    def now(self) -> datetime:
        if not self._timestamps:
            raise ValueError("clock exhausted")
        return self._timestamps.pop(0)


def _verified_evidence(
    *,
    provider_fixture: TinyProviderAttemptFixture,
    command_results_by_id: Mapping[str, CommandRunnerResult],
) -> tuple[VerifiedEvidence, ...]:
    verified: list[VerifiedEvidence] = []
    for obligation in provider_fixture.compiled.ticket_graph_fixture.contracts.contract_gate.evidence_obligations:
        command_result = command_results_by_id[_command_id_for_obligation(obligation)]
        producer_attempt_ref = _producer_attempt_ref_for_obligation(
            provider_fixture=provider_fixture,
            obligation=obligation,
        )
        claim = build_evidence_claim_from_verification_run(
            verification_run=command_result.verification_run,
            evidence_obligation=obligation,
            producer_attempt_ref=producer_attempt_ref,
            acceptance_refs=obligation.acceptance_refs,
            source_surface_refs=obligation.source_surface_refs,
            expected_purpose=EvidencePurpose.IMPLEMENTATION,
            summary=(
                "Tiny package assembly evidence verified from declared runner output."
            ),
        )
        result = EvidenceVerifier().verify(
            EvidenceVerificationInput(
                claim=claim,
                evidence_obligation=obligation,
                active_acceptance_contract=(
                    provider_fixture.compiled.ticket_graph_fixture.contracts.acceptance_contract
                ),
                artifact_manifest=_artifact_manifest(
                    command_result=command_result,
                    producer_attempt_ref=producer_attempt_ref,
                    artifact_kind=obligation.required_artifact_type.value,
                ),
                purpose_policy=EvidencePurposePolicy(
                    rules=(
                        EvidencePurposeRule(
                            required_artifact_type=obligation.required_artifact_type,
                            allowed_purposes=(EvidencePurpose.IMPLEMENTATION,),
                        ),
                    )
                ),
                provider_attempts=tuple(provider_fixture.provider_attempts_by_ticket_id.values()),
                verification_runs=(command_result.verification_run,),
                verified_at=VERIFIED_AT,
            )
        )
        if not result.success or result.verified_evidence is None:
            raise AssertionError(f"tiny evidence verification failed: {result.blockers}")
        verified.append(result.verified_evidence)
    return tuple(verified)


def _producer_attempt_ref_for_obligation(
    *,
    provider_fixture: TinyProviderAttemptFixture,
    obligation: EvidenceObligation,
):
    artifact_type = obligation.required_artifact_type.value
    if artifact_type in {
        "backend_source_inventory",
        "sqlite_persistence_evidence",
    }:
        return provider_fixture.provider_attempts_by_ticket_id[
            TICKET_BACKEND_API_ID
        ].provider_attempt_id
    if artifact_type == "frontend_source_inventory":
        return provider_fixture.provider_attempts_by_ticket_id[
            TICKET_FRONTEND_UI_ID
        ].provider_attempt_id
    if artifact_type == "run_manifest":
        return provider_fixture.provider_attempts_by_ticket_id[
            TICKET_DOCS_RUN_MANIFEST_ID
        ].provider_attempt_id
    return provider_fixture.provider_attempts_by_ticket_id[TICKET_TESTS_ID].provider_attempt_id


def _artifact_manifest(
    *,
    command_result: CommandRunnerResult,
    producer_attempt_ref,
    artifact_kind: str,
) -> ArtifactManifest:
    run = command_result.verification_run
    return ArtifactManifest(
        entries=(
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=run.stdout_ref.value),
                sha256=_sha256(command_result.stdout),
                producer_attempt_ref=producer_attempt_ref,
                source_ref=run.verification_run_id.value,
                artifact_kind=f"{artifact_kind}_stdout",
            ),
            ArtifactManifestEntry(
                artifact_ref=EvidenceArtifactRef(value=run.stderr_ref.value),
                sha256=_sha256(command_result.stderr),
                producer_attempt_ref=producer_attempt_ref,
                source_ref=run.verification_run_id.value,
                artifact_kind=f"{artifact_kind}_stderr",
            ),
        )
    )


def _command_id_for_obligation(obligation: EvidenceObligation) -> str:
    if obligation.required_artifact_type.value in {
        "frontend_backend_integration_evidence",
        "frontend_source_inventory",
        "run_manifest",
        "command_evidence",
    }:
        return "test-integration"
    return "test-backend"


def _write_ephemeral_tiny_package_for_command_evidence(
    *,
    package_root: Path,
    package_contents: Mapping[str, str],
) -> None:
    root_text = package_root.as_posix().rstrip("/")
    if root_text in {"10-project", "20-evidence"} or root_text.endswith(
        "/10-project"
    ) or root_text.endswith("/20-evidence"):
        raise ValueError("tiny package assembly fixture requires an isolated tmp package root")
    resolved_root = package_root.resolve()
    validated_targets: list[tuple[Path, str]] = []
    for relative_path, content in package_contents.items():
        PackageArtifactPath(value=relative_path)
        target = (resolved_root / relative_path).resolve()
        if target == resolved_root or resolved_root not in target.parents:
            raise ValueError("package artifact path must stay within package root")
        validated_targets.append((target, content))
    package_root.mkdir(parents=True, exist_ok=True)
    for target, content in validated_targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _package_contents_with_run_manifest(
    *,
    package_contents: Mapping[str, str],
    run_manifest: RunManifest,
) -> Mapping[str, str]:
    if "run-manifest.json" in package_contents:
        return package_contents
    return {
        **package_contents,
        "run-manifest.json": (
            json.dumps(run_manifest.model_dump(mode="json"), sort_keys=True) + "\n"
        ),
    }


def _validate_physical_run_manifest(
    *,
    package_root: Path,
    run_manifest: RunManifest,
) -> None:
    manifest_path = package_root / "run-manifest.json"
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError("run-manifest.json is required") from error
    except json.JSONDecodeError as error:
        raise ValueError("run-manifest.json must contain valid run manifest JSON") from error
    try:
        physical_manifest = RunManifest.model_validate(data)
    except Exception as error:
        raise ValueError("run-manifest.json must match RunManifest schema") from error
    if physical_manifest != run_manifest:
        raise ValueError("run-manifest.json must match in-memory RunManifest")


def _evidence_refs_by_artifact_type(
    verified_evidence: tuple[VerifiedEvidence, ...],
) -> dict[str, tuple[object, ...]]:
    by_type: dict[str, list[object]] = {}
    for evidence in verified_evidence:
        by_type.setdefault(evidence.required_artifact_type.value, []).append(
            evidence.verified_evidence_id
        )
    return {
        artifact_type: tuple(sorted(refs, key=lambda ref: ref.value))
        for artifact_type, refs in by_type.items()
    }


def _sha256(value: str) -> ArtifactSha256:
    return ArtifactSha256(value=hashlib.sha256(value.encode("utf-8")).hexdigest())


__all__ = [
    "EXPECTED_TINY_PACKAGE_PATHS",
    "TinyPackageAssemblyFixture",
    "build_tiny_package_assembly_fixture",
]
